from audit.config import AuditConfig
from audit.features import Features

KEEP, REVIEW, RELEASE = "KEEP", "REVIEW", "RELEASE"


def classify(f: Features, cfg: AuditConfig,
             protected: set[int] | frozenset = frozenset()) -> tuple[str, list[str]]:
    if f.company_id in protected:
        return KEEP, ["в белом списке"]
    if f.recent_won:
        return KEEP, [f"успешная сделка за последние {cfg.won_days} дн."]
    if f.planned:
        return KEEP, ["есть запланированное дело"]
    if f.open_deals and f.inbound and (f.has_dm or not cfg.require_dm):
        return KEEP, [f"открытых сделок: {f.open_deals}",
                      f"входящих за {cfg.window_days} дн.: {f.inbound}"]

    if not f.open_deals and not f.inbound:
        reasons = ["нет открытых сделок",
                   f"нет входящей коммуникации за {cfg.window_days} дн."]
        if f.outbound:
            reasons.append(f"только исходящие: {f.outbound}")
        if f.only_generic_emails:
            reasons.append("только общие адреса (info@, office@...)")
        return RELEASE, reasons

    reasons = []
    if f.open_deals and not f.inbound:
        reasons.append("есть открытая сделка, но клиент не отвечал")
    if f.open_deals and f.inbound and not f.has_dm:
        reasons.append("сделка и ответы есть, но нет контакта с должностью ЛПР")
    if f.inbound and not f.open_deals:
        reasons.append("клиент отвечал, но открытых сделок нет")
    return REVIEW, reasons
