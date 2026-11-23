import base64
import json
import time
import re
from pathlib import Path
from urllib import response
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from llm_factory import get_llm
from bitrix_client import find_duplicates as _find_dups, create_company as _create_company, create_contact as _create_contact, create_deal as _create_deal
from utils import timeit
from pydantic import BaseModel, ValidationError

class CardData(BaseModel):
    company: str = ""
    first_name: str = ""
    last_name: str = ""
    second_name: str = ""
    position: str = ""
    phones: list[str] = []
    emails: list[str] = []
    notes: str = ""

def _parse_card(text: str) -> CardData:
    m = re.search(r"\{.*\}", text, re.S)   # берём первый JSON-объект, игнорируя обёртки
    if not m:
        raise ValueError("В ответе модели нет JSON")
    return CardData.model_validate_json(m.group(0))

@tool
@timeit
def extract_contact_from_image(image_path: str) -> str:
    """Извлекает контактные данные с изображения визитки.
    Возвращает JSON с полями: company, contact_name, position, phones, emails, notes."""
    path = Path(image_path)
    if not path.exists():
        return json.dumps({"error": f"Файл не найден: {image_path}"})

    # Читаем изображение и кодируем в base64
    image_data = base64.b64encode(path.read_bytes()).decode("utf-8")
    suffix = path.suffix.lower().replace(".", "")
    if suffix == "jpg":
        suffix = "jpeg"

    llm = get_llm()

    # Для Claude и Qwen (OpenAI-совместимые) используем стандартный vision-формат
    # Для GigaChat формат может отличаться, но базовый image_url обычно поддерживается
    message = HumanMessage(content=[
        {
            "type": "text",
            "text": (
                "Распознай визитку на изображении и верни СТРОГО JSON без markdown-обёртки. "
                "Правила заполнения полей:\n"
                "- company: Юридическое название компании (например, 'Beyond the Network Limited'), "
                "если его нет — используй крупный логотип.\n"
                "- first_name, last_name, second_name: имя, фамилия, отчество человека по отдельности "
                "(отчество, если его нет, оставь пустым).\n"
                "- position: Только явно указанная должность (CEO, Manager и т.д.). "
                "- phones: Массив всех телефонов, очищенных от лишних символов, но с сохранением формата.\n"
                "- emails: Массив всех email.\n"
                "- notes: Адрес, сайт, дополнительные примечания.\n"
                "Если поле не найдено — оставь пустую строку или пустой массив."
            ),
        },
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/{suffix};base64,{image_data}"},
        },
    ])

    start_time = time.perf_counter()

    try:
        response = llm.invoke([message])
        elapsed = time.perf_counter() - start_time

        # Извлекаем токены (если провайдер их вернул)
        usage = getattr(response, "usage_metadata", None)
        input_tokens = usage.get("input_tokens", 0) if usage else 0
        output_tokens = usage.get("output_tokens", 0) if usage else 0
        total_tokens = usage.get("total_tokens", 0) if usage else 0

        print(f"\n--- Метрики extract_contact_from_image ---")
        print(f"Время: {elapsed:.2f} сек")
        print(f"Токены (вход/выход/всего): {input_tokens} / {output_tokens} / {total_tokens}")
        print(f"------------------------------------------\n")


        # Пытаемся извлечь JSON из ответа (модель может обернуть в ```json)
        card = _parse_card(response.content)
    except (ValueError, ValidationError) as e:
        return json.dumps({"error": f"Не удалось разобрать ответ модели: {e}"}, ensure_ascii=False)
    return card.model_dump_json()

@tool
def find_bitrix_duplicates(contact_json: str) -> str:
    """Принимает JSON с полями emails (список) и phones (список).
    Ищет дубли контактов и компаний в Bitrix24.
    Возвращает JSON: {'contacts': [id...], 'companies': [id...]}."""
    try:
        data = json.loads(contact_json)
    except json.JSONDecodeError:
        return json.dumps({"error": "Некорректный JSON"})

    emails = data.get("emails", [])
    phones = data.get("phones", [])
    result = _find_dups(emails, phones)
    if result.get("error"):
        return json.dumps({"status": "error",
            "message": "Не удалось проверить дубли из-за ошибки. Создание запрещено."})
    if not result.get("searched"):
        return json.dumps({"status": "error",
            "message": "На визитке нет ни телефона, ни email — проверить дубли нельзя. Нужна ручная проверка."})
    return json.dumps(result, ensure_ascii=False)

@tool
def create_bitrix_company(contact_json: str) -> str:
    """Создает компанию в Bitrix24 на основе JSON. Возвращает JSON с ID компании."""
    data = json.loads(contact_json)
    try:
        company_id = _create_company(data)
        return json.dumps({"company_id": company_id, "status": "success"})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

@tool
def create_bitrix_contact(contact_json: str, company_id: int | None = None) -> str:
    """Создает контакт в Bitrix24; company_id необязателен. Возвращает JSON с ID контакта."""
    try:
        data = json.loads(contact_json)
        contact_id = _create_contact(data, company_id)
        return json.dumps({"contact_id": contact_id, "status": "success"})
    except (json.JSONDecodeError, BitrixError) as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

@tool
def create_bitrix_deal(contact_json: str, company_id: int = None, contact_id: int = None) -> str:
    """Создает сделку в Bitrix24. Возвращает JSON с ID сделки."""
    data = json.loads(contact_json)
    try:
        deal_id = _create_deal(data, company_id, contact_id)
        return json.dumps({"deal_id": deal_id, "status": "success"})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})
