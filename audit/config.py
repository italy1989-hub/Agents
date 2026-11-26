import os
from dataclasses import dataclass, field
from datetime import date

from core.env import env_int, env_str

@dataclass
class AuditConfig:
    term_days: int = 20
    launch_date: date = date(2026, 12, 1)      # день анонса: старт отсчёта для уже закреплённых
    pool_user_id: int | None = field(default_factory=lambda: env_int("AUDIT_POOL_USER_ID"))
    return_date_field: str | None = field(default_factory=lambda: env_str("BITRIX_RETURN_DATE_FIELD"))
    export_days: int = 90                      # за сколько дней выгружаем активности
    max_review_share: float = 0.2              # выше этой доли отчёт предупреждает об аномалии
    simulate: bool = False                     # режим показа: игнорируем журнал ответственных
