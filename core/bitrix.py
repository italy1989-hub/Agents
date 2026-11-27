import os
import requests
import logging
import threading
import time
import re
from dotenv import load_dotenv
from core.utils import timeit
from core.env import env_int, env_str

load_dotenv()

BITRIX_WEBHOOK = os.getenv("BITRIX_WEBHOOK")  # например: https://your-portal.bitrix24.ru/rest/№№№№№/xxxx/
DEFAULT_COUNTRY = os.getenv("DEFAULT_PHONE_COUNTRY", "7")

log = logging.getLogger(__name__)

class BitrixError(Exception):
    pass

_lock = threading.Lock()
_last_call = 0.0
MIN_INTERVAL = 0.5            # ~2 запроса/сек, лимит Bitrix
RETRYABLE_ERRORS = {"QUERY_LIMIT_EXCEEDED", "INTERNAL_SERVER_ERROR"}
WRITE_SUFFIXES = (".add", ".update", ".delete")

class BitrixTimeout(BitrixError):
    """Запись могла пройти на стороне Bitrix, результат неизвестен."""

CONNECT_TIMEOUT = float(os.getenv("BITRIX_CONNECT_TIMEOUT", "5"))
READ_TIMEOUT = float(os.getenv("BITRIX_READ_TIMEOUT", "30"))
WRITE_TIMEOUT = float(os.getenv("BITRIX_WRITE_TIMEOUT", "90"))

def _base_url(is_write: bool) -> str:
    read = env_str("BITRIX_WEBHOOK_READ")
    base = BITRIX_WEBHOOK if (is_write or not read) else read
    if read and not read.startswith("http"):
        raise BitrixError("BITRIX_WEBHOOK_READ должен быть ссылкой вида https://.../rest/<id>/<ключ>/")
    return base.rstrip("/")

def _redact(text: str) -> str:
    """Убирает секретный ключ вебхука из текста (ошибки, логи)."""
    for hook in (BITRIX_WEBHOOK, os.getenv("BITRIX_WEBHOOK_READ")):
        if hook:
            text = text.replace(hook.rstrip("/"), "https://***")
    return re.sub(r"/rest/\d+/[A-Za-z0-9]+", "/rest/***", text)

def _common_fields(assigned_by_id: int | None) -> dict:
    f = {}
    if assigned_by_id:
        f["ASSIGNED_BY_ID"] = assigned_by_id
    source = env_str("BITRIX_SOURCE_ID")
    if source:
        f["SOURCE_ID"] = source
    return f

@timeit
def _call_bitrix(method: str, params: dict, retries: int = 4) -> dict:
    is_write = method.endswith(WRITE_SUFFIXES)
    url = f"{_base_url(is_write)}/{method}"

    global _last_call
    for attempt in range(retries + 1):
        with _lock:  # простое ограничение частоты
            wait = MIN_INTERVAL - (time.monotonic() - _last_call)
            if wait > 0:
                time.sleep(wait)
            _last_call = time.monotonic()

        try:
            resp = requests.post(
                url, json=params,
                timeout=(CONNECT_TIMEOUT, WRITE_TIMEOUT if is_write else READ_TIMEOUT))
        except requests.ConnectTimeout as e:
            # запрос не дошёл до сервера: повтор безопасен даже для записи
            if attempt == retries:
                raise BitrixError(_redact(f"{method}: не удалось подключиться: {e}")) from None
            time.sleep(2 ** attempt)
            continue
        except (requests.Timeout, requests.ConnectionError) as e:
            if is_write:
                raise BitrixTimeout(_redact(f"{method}: нет ответа, запись могла пройти: {e}")) from None
            if attempt == retries:
                raise BitrixError(_redact(f"{method}: сетевая ошибка: {e}")) from None
            time.sleep(2 ** attempt)
            continue

        try:
            data = resp.json()
        except ValueError:
            raise BitrixError(f"{method}: не JSON, HTTP {resp.status_code}")

        err = data.get("error")
        if err:
            if err in RETRYABLE_ERRORS and attempt < retries:
                log.warning("%s: %s, повтор %d", method, err, attempt + 1)
                time.sleep(2 ** attempt)
                continue
            raise BitrixError(f"{method}: {err}: {data.get('error_description', '')}")

        resp.raise_for_status()
        return data

    raise BitrixError(f"{method}: исчерпаны попытки")

EXT = re.compile(r"\s*(?:ext\.?|x|доб\.?|добавочный)\s*\d+\s*$", re.I)

def normalize_phone(raw: str) -> str | None:
    raw = EXT.sub("", raw or "")
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 7:
        return None
    if raw.strip().startswith("+"):
        return "+" + digits
    if len(digits) == 11 and digits[0] == "8":
        return "+7" + digits[1:]
    if len(digits) == 10:
        return "+" + DEFAULT_COUNTRY + digits
    return "+" + digits

def normalize_email(raw: str) -> str | None:
    e = (raw or "").strip().lower()
    return e if "@" in e else None

def _extract_ids(data: dict, entity_key: str) -> list:
    res = data.get("result")
    if isinstance(res, dict):
        return res.get(entity_key, [])
    if isinstance(res, list):
        return res
    return []

def find_duplicates(emails: list[str], phones: list[str]) -> dict:
    emails = sorted({e for e in map(normalize_email, emails or []) if e})
    phones = sorted({p for p in map(normalize_phone, phones or []) if p})

    result = {"contacts": [], "companies": [], "error": False, "searched": False}
    queries = []
    for etype, key in (("CONTACT", "contacts"), ("COMPANY", "companies")):
        if emails:
            queries.append((etype, "EMAIL", emails, key))
        if phones:
            queries.append((etype, "PHONE", phones, key))

    result["searched"] = bool(queries)
    for etype, ctype, values, key in queries:
        try:
            data = _call_bitrix("crm.duplicate.findbycomm", {
                "entity_type": etype, "type": ctype, "values": values[:20],
            })
            result[key].extend(_extract_ids(data, etype))
        except BitrixError as e:
            log.error("Поиск дублей %s/%s: %s", etype, ctype, e)
            result["error"] = True

    result["contacts"] = sorted(set(result["contacts"]))
    result["companies"] = sorted(set(result["companies"]))
    return result

# Читаем настройки тестового режима
TEST_MODE = os.getenv("TEST_MODE", "True").lower() == "true"
TEST_MARKER = os.getenv("TEST_MARKER", "@TEST@")

def _add_marker(text: str) -> str:
    """Добавляет маркер к тексту, если включен тестовый режим."""
    if TEST_MODE and text:
        return f"{TEST_MARKER} {text}"
    elif TEST_MODE:
        return TEST_MARKER
    return text

def _add_checked(add_method: str, list_method: str, payload: dict, flt: dict) -> int:
    """Создаёт запись; после таймаута проверяет, не создалась ли она."""
    try:
        return _call_bitrix(add_method, payload).get("result")
    except BitrixTimeout:
        time.sleep(3)  # даём Bitrix дописать
        found = _call_bitrix(list_method, {
            "filter": flt, "select": ["ID"], "order": {"ID": "DESC"},
        }).get("result", [])
        if len(found) == 1:
            log.warning("%s: таймаут, но запись найдена: %s", add_method, found[0]["ID"])
            return int(found[0]["ID"])
        raise  # 0 или несколько совпадений: решает человек

@timeit
def create_company(company_data: dict, assigned_by_id: int | None = None) -> int:
    """Создает компанию в Битрикс24. Возвращает ID."""
    title = company_data.get("company") or "Без названия"
    notes = company_data.get("notes", "")

    payload = {
        "fields": {
            "TITLE": _add_marker(title),
            "COMMENTS": _add_marker(notes)
        }
    }

    # Добавляем телефоны и email, если они есть
    if company_data.get("phones"):
        payload["fields"]["PHONE"] = [{"VALUE": p, "VALUE_TYPE": "WORK"} for p in company_data["phones"]]
    if company_data.get("emails"):
        payload["fields"]["EMAIL"] = [{"VALUE": e, "VALUE_TYPE": "WORK"} for e in company_data["emails"]]

    payload["fields"].update(_common_fields(assigned_by_id))
    return _add_checked("crm.company.add", "crm.company.list", payload,
                    {"TITLE": payload["fields"]["TITLE"]})

PATRONYMIC = re.compile(r"(ович|евич|ьич|овна|евна|ична)$", re.I)

def split_name(full: str) -> tuple[str, str, str]:
    """Запасной вариант: (имя, фамилия, отчество). Надёжен только для русских ФИО из 3 слов."""
    p = full.split()
    if len(p) == 3:
        if PATRONYMIC.search(p[2]):   # Фамилия Имя Отчество
            return p[1], p[0], p[2]
        if PATRONYMIC.search(p[1]):   # Имя Отчество Фамилия
            return p[0], p[2], p[1]
    if len(p) == 2:
        return p[0], p[1], ""
    return (p[0] if p else ""), "", ""

@timeit
def create_contact(contact_data: dict, company_id: int | None = None,
                   assigned_by_id: int | None = None) -> int:
    """Создает контакт. Возвращает ID."""
    if contact_data.get("first_name") or contact_data.get("last_name"):
        first, last, second = (contact_data.get("first_name", ""),
                            contact_data.get("last_name", ""),
                            contact_data.get("second_name", ""))
    else:
        first, last, second = split_name(contact_data.get("contact_name", ""))

    payload = {
        "fields": {
            "NAME": _add_marker(first),
            "LAST_NAME": _add_marker(last) if last else "",
            "SECOND_NAME": _add_marker(second) if second else "",
            "POST": contact_data.get("position", ""),
            "COMMENTS": _add_marker("Создано из визитки"),
        }
    }

    if company_id:
        payload["fields"]["COMPANY_ID"] = company_id
    if contact_data.get("phones"):
        payload["fields"]["PHONE"] = [{"VALUE": p, "VALUE_TYPE": "WORK"} for p in contact_data["phones"]]
    if contact_data.get("emails"):
        payload["fields"]["EMAIL"] = [{"VALUE": e, "VALUE_TYPE": "WORK"} for e in contact_data["emails"]]

    flt = {"NAME": payload["fields"]["NAME"], "LAST_NAME": payload["fields"]["LAST_NAME"]}
    if company_id:
        flt["COMPANY_ID"] = company_id
    payload["fields"].update(_common_fields(assigned_by_id))
    return _add_checked("crm.contact.add", "crm.contact.list", payload, flt)

@timeit
def create_deal(contact_data: dict, company_id: int | None = None, contact_id: int | None = None,
                assigned_by_id: int | None = None) -> int:
    """Создает сделку. Возвращает ID."""
    title = f"Сделка: {contact_data.get('company') or 'Новая сделка'}"

    payload = {
        "fields": {
            "TITLE": _add_marker(title),
            "COMMENTS": _add_marker("Создано ИИ-агентом из визитки"),
        }
    }

    if company_id:
        payload["fields"]["COMPANY_ID"] = company_id
    if contact_id:
        payload["fields"]["CONTACT_ID"] = contact_id

    flt = {"TITLE": payload["fields"]["TITLE"]}
    if company_id:
        flt["COMPANY_ID"] = company_id
    payload["fields"].update(_common_fields(assigned_by_id))
    category, stage = env_int("BITRIX_DEAL_CATEGORY_ID"), env_str("BITRIX_DEAL_STAGE_ID")
    if category:
        payload["fields"]["CATEGORY_ID"] = category
    if stage:
        payload["fields"]["STAGE_ID"] = stage
    return _add_checked("crm.deal.add", "crm.deal.list", payload, flt)

def find_open_deals(company_id: int | None = None, contact_id: int | None = None) -> list[dict]:
    """Открытые сделки по контакту или компании, с ответственным."""
    if contact_id:
        flt = {"CONTACT_ID": contact_id, "CLOSED": "N"}
    elif company_id:
        flt = {"COMPANY_ID": company_id, "CLOSED": "N"}
    else:
        return []
    data = _call_bitrix("crm.deal.list", {
        "filter": flt,
        "select": ["ID", "TITLE", "ASSIGNED_BY_ID", "STAGE_ID"],
    })
    return data.get("result", [])
