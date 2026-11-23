import os
import requests
import logging
import threading
import time
import re
from dotenv import load_dotenv
from utils import timeit

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

@timeit
def _call_bitrix(method: str, params: dict, retries: int = 4) -> dict:
    if not BITRIX_WEBHOOK:
        raise BitrixError("BITRIX_WEBHOOK не задан в .env")
    url = f"{BITRIX_WEBHOOK.rstrip('/')}/{method}"
    is_write = method.endswith(WRITE_SUFFIXES)

    global _last_call
    for attempt in range(retries + 1):
        with _lock:  # простое ограничение частоты
            wait = MIN_INTERVAL - (time.monotonic() - _last_call)
            if wait > 0:
                time.sleep(wait)
            _last_call = time.monotonic()

        try:
            resp = requests.post(url, json=params, timeout=10)
        except (requests.Timeout, requests.ConnectionError) as e:
            # после таймаута запись могла пройти — повторять нельзя
            if is_write or attempt == retries:
                raise BitrixError(f"{method}: сетевая ошибка: {e}") from e
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

def normalize_phone(raw: str) -> str | None:
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
TEST_MARKER = os.getenv("TEST_MARKER", "[@TEST@]")

def _add_marker(text: str) -> str:
    """Добавляет маркер к тексту, если включен тестовый режим."""
    if TEST_MODE and text:
        return f"{TEST_MARKER} {text}"
    elif TEST_MODE:
        return TEST_MARKER
    return text

@timeit
def create_company(company_data: dict) -> int:
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

    data = _call_bitrix("crm.company.add", payload)
    return data.get("result")

@timeit
def create_contact(contact_data: dict, company_id: int = None) -> int:
    """Создает контакт. Возвращает ID."""
    full_name = contact_data.get("contact_name", "")
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

    # внутри create_contact:
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

    data = _call_bitrix("crm.contact.add", payload)
    return data.get("result")

@timeit
def create_deal(contact_data: dict, company_id: int = None, contact_id: int = None) -> int:
    """Создает сделку. Возвращает ID."""
    title = f"Сделка: {contact_data.get('company', 'Новая сделка')}"

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

    data = _call_bitrix("crm.deal.add", payload)
    return data.get("result")
