import os


def env_int(name: str) -> int | None:
    """Целое число из .env. Пусто = не задано, мусор = понятная ошибка."""
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{name} в .env должно быть целым числом, сейчас: {raw!r}. "
                         "Укажите число или закомментируйте строку.") from None


def env_str(name: str) -> str | None:
    """Строка из .env. Пусто = не задано, заглушка вида <...> = понятная ошибка."""
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return None
    if raw.startswith("<") and raw.endswith(">"):
        raise ValueError(f"{name} в .env содержит заглушку {raw!r}. "
                         "Укажите реальное значение или закомментируйте строку.")
    return raw
