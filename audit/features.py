import json
from dataclasses import dataclass, field
from datetime import date

GENERIC_LOCALS = {"info", "office", "sales", "contact", "contacts", "mail", "admin", "hello",
                  "support", "service", "zakaz", "post", "secretary", "reception", "general"}

FACTS_SQL = """
SELECT c.id, c.title, c.manager_id, c.emails, c.return_date,
  (SELECT MAX(o.since) FROM ownership o WHERE o.company_id = c.id) AS assigned_since,
  MAX(CASE WHEN a.direction = 1 THEN a.created END) AS last_inbound,
  COUNT(a.id) AS activities_total
FROM companies c LEFT JOIN activities a ON a.company_id = c.id
GROUP BY c.id
"""


@dataclass
class CompanyFacts:
    company_id: int
    title: str
    manager_id: int | None
    assigned_since: date | None = None
    return_date: date | None = None
    last_inbound: date | None = None
    next_step: str | None = None
    next_step_deadline: date | None = None
    managers: set[int] = field(default_factory=set)
    cards: int = 0
    activities_total: int = 0
    only_generic_emails: bool = False
    contact_ids: list[int] = field(default_factory=list)
    deal_ids: list[int] = field(default_factory=list)


def _d(s: str | None) -> date | None:
    return date.fromisoformat(s[:10]) if s else None


def compute_facts(db, today: date) -> list[CompanyFacts]:
    contacts: dict[int, list] = {}
    for r in db.execute("SELECT id, company_id, manager_id, emails FROM contacts "
                        "WHERE company_id IS NOT NULL"):
        contacts.setdefault(r["company_id"], []).append(r)

    deals: dict[int, list] = {}  # только открытые сделки («в процессе»)
    for r in db.execute("SELECT id, company_id, manager_id FROM deals "
                        "WHERE company_id IS NOT NULL AND stage_semantic = 'P'"):
        deals.setdefault(r["company_id"], []).append(r)

    steps: dict[int, object] = {}  # ближайшее запланированное дело со сроком
    for r in db.execute("SELECT company_id, subject, deadline FROM activities "
                        "WHERE completed = 'N' AND deadline >= ? AND company_id IS NOT NULL "
                        "ORDER BY deadline", (today.isoformat(),)):
        steps.setdefault(r["company_id"], r)

    result = []
    for r in db.execute(FACTS_SQL):
        cts, dls = contacts.get(r["id"], []), deals.get(r["id"], [])
        managers = {m for m in [r["manager_id"], *(x["manager_id"] for x in cts),
                                *(x["manager_id"] for x in dls)] if m}
        addrs = json.loads(r["emails"] or "[]")
        for ct in cts:
            addrs += json.loads(ct["emails"] or "[]")
        step = steps.get(r["id"])
        result.append(CompanyFacts(
            company_id=r["id"], title=r["title"] or "", manager_id=r["manager_id"],
            assigned_since=_d(r["assigned_since"]), return_date=_d(r["return_date"]),
            last_inbound=_d(r["last_inbound"]),
            next_step=step["subject"] if step else None,
            next_step_deadline=_d(step["deadline"]) if step else None,
            managers=managers, cards=len(cts) + len(dls),
            activities_total=r["activities_total"],
            only_generic_emails=bool(addrs) and all(
                a.split("@")[0].lower() in GENERIC_LOCALS for a in addrs),
            contact_ids=[x["id"] for x in cts], deal_ids=[x["id"] for x in dls]))
    return result
