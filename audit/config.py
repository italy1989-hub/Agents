from dataclasses import dataclass


@dataclass
class AuditConfig:
    window_days: int = 180        # окно, где ищем живую коммуникацию
    won_days: int = 365           # успешная сделка за этот срок защищает компанию
    require_dm: bool = False      # для KEEP требовать контакт с должностью ЛПР
    max_release_share: float = 0.2  # выше этой доли отчёт предупреждает об аномалии
