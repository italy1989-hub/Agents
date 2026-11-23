from langchain_core.messages import HumanMessage
from agent import graph
from langchain_core.messages import SystemMessage

system_prompt = SystemMessage(content=(
    "Ты — ассистент по работе с CRM. Обработай визитку строго по шагам.\n"
    "1. Вызови extract_contact_from_image. Если в ответе есть поле error — остановись и сообщи об ошибке.\n"
    "2. Вызови find_bitrix_duplicates, передав JSON с полями emails и phones из шага 1. "
    "Если вернулся status=error — остановись и ничего не создавай.\n"
    "3. По результату поиска:\n"
    "   а) контактов и компаний нет → create_bitrix_company, затем create_bitrix_contact "
    "(с company_id), затем create_bitrix_deal (с company_id и contact_id);\n"
    "   б) компания найдена, контакта нет → create_bitrix_contact с company_id найденной компании, "
    "затем create_bitrix_deal;\n"
    "   в) контакт найден → ничего не создавай, сообщи ID найденных записей.\n"
    "4. В конце перечисли ID созданных или найденных записей.\n"
    "Правила: никогда не выдумывай ID; JSON с визитки передавай в инструменты без изменений."
))

# Эмуляция: пользователь прислал путь к визитке
user_input = "Обработай визитку: ./test/cards/card04.jpg"

result = graph.invoke({
    "messages": [
        system_prompt,
        HumanMessage(content=user_input)
    ]
})

# Выводим все сообщения, чтобы увидеть, какие инструменты вызывались
for msg in result["messages"]:
    print(f"\n--- {msg.__class__.__name__} ---")
    if hasattr(msg, "content") and msg.content:
        print(msg.content)
    if hasattr(msg, "tool_calls") and msg.tool_calls:
        print(f"Вызов инструмента: {msg.tool_calls[0]['name']}")
        print(f"Аргументы: {msg.tool_calls[0]['args']}")
