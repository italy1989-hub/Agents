import os
import requests
from dotenv import load_dotenv
from utils import timeit

load_dotenv()

BITRIX_WEBHOOK = os.getenv("BITRIX_WEBHOOK")  # например: https://your-portal.bitrix24.ru/rest/№№№№№/xxxx/

@timeit
def _call_bitrix(method: str, params: dict) -> dict:
    url = f"{BITRIX_WEBHOOK}{method}"
    resp = requests.post(url, json=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def find_duplicates(emails: list[str], phones: list[str]) -> dict:
    """Ищет дубли контактов и компаний по email и телефонам.
    Возвращает {'contacts': [...], 'companies': [...], 'error': bool}."""
    result = {"contacts": [], "companies": [], "error": False}

    def _extract_ids(data, entity_key):
        """Безопасно извлекает ID из ответа API (обрабатывает dict и list)."""
        res = data.get("result")
        if not res:
            return []
        if isinstance(res, dict):
            return res.get(entity_key, [])
        if isinstance(res, list):
            # Если API вернул просто список ID
            return res
        return []

    # Поиск по email среди контактов
    if emails:
        try:
            data = _call_bitrix("crm.duplicate.findbycomm", {
                "entity_type": "CONTACT",
                "type": "EMAIL",
                "values": emails[:20],
            })
            result["contacts"].extend(_extract_ids(data, "CONTACT"))
        except Exception as e:
            print(f"Ошибка поиска по email: {e}")
            result["error"] = True

    # Поиск по телефонам среди контактов
    if phones:
        try:
            data = _call_bitrix("crm.duplicate.findbycomm", {
                "entity_type": "CONTACT",
                "type": "PHONE",
                "values": phones[:20],
            })
            result["contacts"].extend(_extract_ids(data, "CONTACT"))
        except Exception as e:
            print(f"Ошибка поиска по телефону: {e}")
            result["error"] = True

    # Поиск компаний по телефонам
    if phones:
        try:
            data = _call_bitrix("crm.duplicate.findbycomm", {
                "entity_type": "COMPANY",
                "type": "PHONE",
                "values": phones[:20],
            })
            result["companies"].extend(_extract_ids(data, "COMPANY"))
        except Exception as e:
            print(f"Ошибка поиска компаний: {e}")
            result["error"] = True

    # Убираем дубли ID
    result["contacts"] = list(set(result["contacts"]))
    result["companies"] = list(set(result["companies"]))
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
    # Простое разделение ФИО (пока так, потом заменим)
    name_parts = full_name.split()
    first_name = name_parts[0] if name_parts else ""
    last_name = name_parts[1] if len(name_parts) > 1 else ""
    second_name = name_parts[2] if len(name_parts) > 2 else ""

    payload = {
        "fields": {
            "NAME": _add_marker(first_name),
            "LAST_NAME": _add_marker(last_name) if last_name else "",
            "SECOND_NAME": _add_marker(second_name) if second_name else "",
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
