from llm_factory import get_llm

llm = get_llm()
response = llm.invoke("Ответь одним словом: работает?")
print(f"Модель: {llm.__class__.__name__}")
print(f"Ответ: {response.content}")
