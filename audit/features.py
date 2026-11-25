import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from audit.config import AuditConfig

DM_RE = re.compile(
    r"директор|руковод|владелец|основател|учредител|управляющ|председател|"
    r"\bceo\b|\bcoo\b|\bcto\b|\bcfo\b|founder|owner|president|\bhead\b|director|partner", re.I)
GENERIC_LOCALS = {"info", "office", "sales", "contact", "contacts", "mail", "admin", "hello",
                  "support", "service", "zakaz", "post", "secretary", "reception", "general"}

FEATURE_SQL = """
SELECT c.id, c.title, c.manager_id, c.emails,
  (SELECT COUNT(*) FROM deals d
     WHERE d.company_id = c.id AND d.stage_semantic = 'P') AS open_deals,
  (SELECT COUNT(*) FROM deals d
     WHERE d.company_id = c.id AND d.stage_semantic = 'S' AND d.date_modify >= :won_since) AS recent_won,
  COALESCE(SUM(a.direction = 1 AND a.created >= :since), 0) AS inbound,
  COALESCE(SUM(a.direction = 2 AND a.created >= :since), 0) AS outbound,
  COALESCE(SUM(a.completed = 'N' AND a.deadline >= :now), 0) AS planned,
  MAX(CASE WHEN a.direction = 1 THEN a.created END) AS last_inbound,
  MAX(a.created) AS last_any
FROM companies c LEFT JOIN activities a ON a.company_id = c.id
GROUP BY c.id
"""


@dataclass
class Features:
    company_id: int
    title: str
    manager_id: int | None
    open_deals: int = 0
    recent_won: int = 0
    inbound: int = 0
    outbound: int = 0
    planned: int = 0
    last_inbound: str | None = None
    last_any: str | None = None
    has_dm: bool = False
    only_generic_emails: bool = False


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def compute_features(db, cfg: AuditConfig, now: datetime | None = None) -> list[Features]:
    """now: UTC-время без tzinfo (для тестов можно задать)."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    params = {"now": _fmt(now),
              "since": _fmt(now - timedelta(days=cfg.window_days)),
              "won_since": _fmt(now - timedelta(days=cfg.won_days))}

    contacts: dict[int, list] = {}
    for r in db.execute("SELECT company_id, post, emails FROM contacts WHERE company_id IS NOT NULL"):
        contacts.setdefault(r["company_id"], []).append(r)

    result = []
    for r in db.execute(FEATURE_SQL, params):
        cts = contacts.get(r["id"], [])
        addrs = json.loads(r["emails"] or "[]")
        for ct in cts:
            addrs += json.loads(ct["emails"] or "[]")
        result.append(Features(
            company_id=r["id"], title=r["title"] or "", manager_id=r["manager_id"],
            open_deals=r["open_deals"], recent_won=r["recent_won"],
            inbound=r["inbound"], outbound=r["outbound"], planned=r["planned"],
            last_inbound=r["last_inbound"], last_any=r["last_any"],
            has_dm=any(DM_RE.search(ct["post"] or "") for ct in cts),
            only_generic_emails=bool(addrs) and all(
                a.split("@")[0].lower() in GENERIC_LOCALS for a in addrs),
        ))
    return result
