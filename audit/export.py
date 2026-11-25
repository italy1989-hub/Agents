import json
import logging
from datetime import datetime, timedelta, timezone

from core import bitrix as bx
from audit.db import connect

log = logging.getLogger(__name__)

ATTACH_SQL = """
UPDATE activities SET company_id = CASE owner_type_id
    WHEN 4 THEN owner_id
    WHEN 3 THEN (SELECT company_id FROM contacts WHERE contacts.id = activities.owner_id)
    WHEN 2 THEN (SELECT company_id FROM deals WHERE deals.id = activities.owner_id)
END
"""


def _utc(s: str | None) -> str | None:
    """Приводит дату Bitrix к UTC-строке, которую можно сравнивать лексикографически."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None


def _int(v) -> int | None:
    return int(v) if v not in (None, "", "0", 0) else None


def _values(field) -> str:
    return json.dumps([x["VALUE"] for x in (field or []) if x.get("VALUE")], ensure_ascii=False)


def iter_list(method: str, select: list[str], flt: dict | None = None):
    """Читает все записи метода *.list. Только чтение."""
    if not method.endswith(".list"):
        raise ValueError(f"Экспорт умеет только читать (*.list), получено: {method}")
    last_id, n = 0, 0
    while True:
        data = bx._call_bitrix(method, {
            "filter": {**(flt or {}), ">ID": last_id},
            "select": select, "order": {"ID": "ASC"}, "start": -1})
        rows = data.get("result", [])
        if not rows:
            return
        yield from rows
        if n // 1000 != (n + len(rows)) // 1000:
            log.info("%s: выгружено ~%d", method, n + len(rows))
        n += len(rows)
        last_id = int(rows[-1]["ID"])


def _export_users(db):
    for active in (True, False):  # уволенные тоже нужны: за ними могут числиться компании
        start = 0
        while True:
            data = bx._call_bitrix("user.get", {"FILTER": {"ACTIVE": active}, "start": start})
            for u in data.get("result", []):
                name = f'{u.get("NAME", "")} {u.get("LAST_NAME", "")}'.strip()
                db.execute("INSERT OR REPLACE INTO users VALUES (?, ?)", (int(u["ID"]), name))
            if "next" not in data:
                break
            start = data["next"]


def export_all(activity_days: int = 365, db_path: str | None = None) -> None:
    db = connect(db_path)
    since = (datetime.now(timezone.utc) - timedelta(days=activity_days)).strftime("%Y-%m-%dT%H:%M:%S")

    with db:  # одна транзакция: при ошибке остаётся предыдущий снимок
        for table in ("users", "companies", "contacts", "deals", "activities"):
            db.execute(f"DELETE FROM {table}")

        try:
            _export_users(db)
        except bx.BitrixError as e:
            log.warning("user.get недоступен (%s), в отчёте будут ID вместо имён", e)

        for r in iter_list("crm.company.list",
                           ["ID", "TITLE", "ASSIGNED_BY_ID", "DATE_CREATE", "DATE_MODIFY", "EMAIL", "PHONE"]):
            db.execute("INSERT INTO companies VALUES (?,?,?,?,?,?,?)", (
                int(r["ID"]), r.get("TITLE"), _int(r.get("ASSIGNED_BY_ID")),
                _utc(r.get("DATE_CREATE")), _utc(r.get("DATE_MODIFY")),
                _values(r.get("EMAIL")), _values(r.get("PHONE"))))

        for r in iter_list("crm.contact.list",
                           ["ID", "NAME", "LAST_NAME", "POST", "COMPANY_ID", "ASSIGNED_BY_ID", "EMAIL"]):
            db.execute("INSERT INTO contacts VALUES (?,?,?,?,?,?)", (
                int(r["ID"]), f'{r.get("NAME") or ""} {r.get("LAST_NAME") or ""}'.strip(),
                r.get("POST"), _int(r.get("COMPANY_ID")), _int(r.get("ASSIGNED_BY_ID")),
                _values(r.get("EMAIL"))))

        for r in iter_list("crm.deal.list",
                           ["ID", "TITLE", "COMPANY_ID", "CONTACT_ID", "ASSIGNED_BY_ID", "STAGE_ID",
                            "STAGE_SEMANTIC_ID", "CLOSED", "CATEGORY_ID", "DATE_CREATE", "DATE_MODIFY"]):
            db.execute("INSERT INTO deals VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
                int(r["ID"]), r.get("TITLE"), _int(r.get("COMPANY_ID")), _int(r.get("CONTACT_ID")),
                _int(r.get("ASSIGNED_BY_ID")), r.get("STAGE_ID"), r.get("STAGE_SEMANTIC_ID"),
                r.get("CLOSED"), _int(r.get("CATEGORY_ID")),
                _utc(r.get("DATE_CREATE")), _utc(r.get("DATE_MODIFY"))))

        for r in iter_list("crm.activity.list",
                           ["ID", "OWNER_TYPE_ID", "OWNER_ID", "TYPE_ID", "PROVIDER_ID", "DIRECTION",
                            "COMPLETED", "CREATED", "DEADLINE"],
                           flt={">=CREATED": since}):
            db.execute("INSERT INTO activities VALUES (?,?,?,NULL,?,?,?,?,?,?)", (
                int(r["ID"]), _int(r.get("OWNER_TYPE_ID")), _int(r.get("OWNER_ID")),
                _int(r.get("TYPE_ID")), r.get("PROVIDER_ID"), _int(r.get("DIRECTION")),
                r.get("COMPLETED"), _utc(r.get("CREATED")), _utc(r.get("DEADLINE"))))

        db.execute(ATTACH_SQL)  # привязываем каждую активность к компании
        db.execute("INSERT OR REPLACE INTO meta VALUES ('exported_at', ?)",
                   (datetime.now(timezone.utc).isoformat(),))
    log.info("Экспорт завершён")
