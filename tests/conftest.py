import pytest

ENV_KEYS = ["AUDIT_POOL_USER_ID", "BITRIX_RETURN_DATE_FIELD", "BITRIX_SOURCE_ID",
            "BITRIX_DEAL_CATEGORY_ID", "BITRIX_DEAL_STAGE_ID", "BITRIX_WEBHOOK_READ", "UI_PASSWORD"]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Тесты не должны зависеть от .env разработчика."""
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
