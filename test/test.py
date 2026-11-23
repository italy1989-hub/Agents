from langchain_gigachat.chat_models import GigaChat

# Передайте ваш постоянный ключ Authorization Key
giga = GigaChat(
    credentials="MDFhMWY3ODMtYWMzYS03NGNkLWIwN2QtODAxN2Q5ZDNlYjhhOjk3NWI2ZDM3LWIyMDUtNDYyZi1hOWUzLTA4MTcwMmNjMjhjMA==",
    model="GigaChat-2",
    verify_ssl_certs=False, # временно отключите проверку SSL при локальном тестировании
    scope="GIGACHAT_API_PERS" # по умолчанию используется версия для физических лиц
)

print(giga.invoke("Привет!"))
