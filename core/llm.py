import os
from dotenv import load_dotenv
from langchain_core.language_models import BaseChatModel

load_dotenv()


def get_llm() -> BaseChatModel:
    """
    Возвращает LLM в зависимости от переменной окружения LLM_PROVIDER.
    Поддерживает: gigachat, claude, qwen.
    """
    provider = os.getenv("LLM_PROVIDER", "gigachat").lower()

    if provider == "gigachat":
        # Официальный пакет от Сбера для LangChain/LangGraph [citation:14]
        from langchain_gigachat.chat_models import GigaChat

        return GigaChat(
            credentials=os.getenv("GIGACHAT_CREDENTIALS"),
            scope=os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS"),
            model=os.getenv("GIGACHAT_MODEL", "GigaChat"),
            verify_ssl_certs=os.getenv("GIGACHAT_VERIFY_SSL", "false").lower() == "true",  # Для тестового контура Сбера
            streaming=False,
            auto_upload_attachments=True,
            timeout=120.0,
        )

    elif provider == "claude":
        # Официальная интеграция Anthropic для LangChain
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            temperature=0.1,  # Для CRM-задач нужна предсказуемость
        )

    elif provider == "qwen":
        # Локальный Qwen через OpenAI-совместимый эндпоинт (Ollama/vLLM)
        # Это стандартный паттерн для локальных моделей в LangGraph [citation:1][citation:13]
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=os.getenv("QWEN_MODEL", "qwen2.5:7b"),
            api_key=os.getenv("QWEN_API_KEY", "ollama"),
            base_url=os.getenv("QWEN_BASE_URL", "http://localhost:11434/v1"),
            temperature=0.1,
        )

    else:
        raise ValueError(f"Неизвестный LLM_PROVIDER: {provider}. Допустимо: gigachat, claude, qwen.")
