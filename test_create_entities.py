import os
import json
from dotenv import load_dotenv
from bitrix_client import create_company, create_contact, create_deal

# Загружаем переменные из .env
load_dotenv()

def confirm_step(message: str) -> bool:
    """Спрашивает у пользователя разрешение на продолжение."""
    ans = input(f"\n{message} (y/n): ").strip().lower()
    if ans == 'y':
        return True
    print("Пропущено/Остановлено.")
    return False

# Искусственные данные, имитирующие вывод extract_contact_from_image
mock_data = {
    "company": "ООО Ромашка",
    "contact_name": "Иванов Иван Иванович",
    "position": "Директор",
    "phones": ["+79991112233"],
    "emails": ["ivanov@romashka.ru"],
    "notes": "Тестовые данные для проверки API"
}

print("=== ТЕСТИРОВАНИЕ ИНСТРУМЕНТОВ BITRIX API ===")
print(f"Текущий режим теста (TEST_MODE): {os.getenv('TEST_MODE', 'не задан')}")
print(f"Текущий префикс (TEST_MARKER): {os.getenv('TEST_MARKER', 'не задан')}")

# --- ШАГ 1: Создание компании ---
if confirm_step("1. Создать компанию?"):
    try:
        print("Отправка запроса в Bitrix...")
        company_id = create_company(mock_data)
        print(f"✅ УСПЕХ! Создана компания с ID: {company_id}")
    except Exception as e:
        print(f"❌ ОШИБКА: {e}")
        company_id = None
else:
    company_id = None

# --- ШАГ 2: Создание контакта ---
if company_id and confirm_step("2. Создать контакт и привязать к компании?"):
    try:
        print("Отправка запроса в Bitrix...")
        contact_id = create_contact(mock_data, company_id)
        print(f"✅ УСПЕХ! Создан контакт с ID: {contact_id}")
    except Exception as e:
        print(f"❌ ОШИБКА: {e}")
        contact_id = None
else:
    contact_id = None

# --- ШАГ 3: Создание сделки ---
if company_id and contact_id and confirm_step("3. Создать сделку и привязать к компании и контакту?"):
    try:
        print("Отправка запроса в Bitrix...")
        deal_id = create_deal(mock_data, company_id, contact_id)
        print(f"✅ УСПЕХ! Создана сделка с ID: {deal_id}")
    except Exception as e:
        print(f"❌ ОШИБКА: {e}")
else:
    print("Сделка не создана (нет ID компании или контакта, либо отменено пользователем).")

print("\n=== ТЕСТИРОВАНИЕ ЗАВЕРШЕНО ===")
