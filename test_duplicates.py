import json
from bitrix_client import find_duplicates

# Используем реальные данные любого контакта из bitrix
contact_data = {
    "emails": ["ads.notifications@vk.company"],
    "phones": [""]
}

print("Ищем дубли для:", contact_data)
result = find_duplicates(
    emails=contact_data["emails"],
    phones=contact_data["phones"]
)

print("\nРезультат поиска:")
print(json.dumps(result, indent=2, ensure_ascii=False))

if not result["contacts"] and not result["companies"]:
    print("\nДублей не найдено. Можно создавать новые записи.")
else:
    print(f"\nНайдены дубли! Контакты: {result['contacts']}, Компании: {result['companies']}")
