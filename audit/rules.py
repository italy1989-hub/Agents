from dataclasses import dataclass, field
from datetime import date, timedelta

from audit.config import AuditConfig
from audit.features import CompanyFacts

POOL = "В ПУЛЕ"
ACTIVE = "СРОК ИДЁТ"
EXPIRED = "СРОК ИСТЁК, РАБОТА НЕ ПОДТВЕРЖДЕНА"
EXPIRED_PLAN = "СРОК ИСТЁК, ЕСТЬ ШАГ СО СРОКОМ"
REVIEW_STATUSES = {EXPIRED, EXPIRED_PLAN}

FLAG_MISMATCH = "РАСХОЖДЕНИЕ ОТВЕТСТВЕННЫХ"
FLAG_NO_DATA = "НЕДОСТАТОЧНО ДАННЫХ"


@dataclass
class Verdict:
    status: str
    start: date | None = None
    end: date | None = None
    flags: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def term_end(start: date, last_comm: date | None, return_date: date | None, term_days: int) -> date:
    """Правило 4: срок идёт от старта, продлевается общением после старта,
    а дата «вернуться» удерживает компанию до этого дня."""
    base = last_comm if (last_comm and last_comm >= start) else start
    end = base + timedelta(days=term_days)
    return max(end, return_date) if return_date else end


def evaluate(f: CompanyFacts, cfg: AuditConfig, today: date) -> Verdict:
    if cfg.pool_user_id is not None and f.manager_id == cfg.pool_user_id:
        return Verdict(POOL, reasons=["закреплена за техническим аккаунтом (свободный пул)"])

    flags = []
    if len(f.managers) > 1:
        flags.append(FLAG_MISMATCH)
    if f.manager_id is None or (f.cards == 0 and f.activities_total == 0):
        flags.append(FLAG_NO_DATA)

    since = None if cfg.simulate else f.assigned_since       # в симуляции журнал не учитываем
    start = max(since or cfg.launch_date, cfg.launch_date)
    end = term_end(start, f.last_inbound, f.return_date, cfg.term_days)

    if today <= end:
        return Verdict(ACTIVE, start, end, flags, [f"срок до {end:%d.%m.%Y}"])

    reasons = [f"срок истёк {end:%d.%m.%Y}"]
    if f.last_inbound and f.last_inbound >= start:
        reasons.append(f"последнее входящее {f.last_inbound:%d.%m.%Y}")
    else:
        reasons.append("нет входящего общения после начала отсчёта")
    if f.only_generic_emails:
        reasons.append("только общие адреса (info@, office@...)")
    if f.next_step_deadline:
        reasons.append(f"есть запланированный шаг на {f.next_step_deadline:%d.%m.%Y}")
        return Verdict(EXPIRED_PLAN, start, end, flags, reasons)
    return Verdict(EXPIRED, start, end, flags, reasons)
