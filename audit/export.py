import json
import logging
from datetime import datetime, timedelta, timezone

from core import bitrix as bx
from audit.db import connect
from audit.config import AuditConfig
from audit.ledger import update_ledger

log = logging.getLogger(__name__)

def _day(s: str | None) -> str | None:
    return s[:10] if s else None

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

def _int0(v) -> int | None:
    """Как _int, но 0 остаётся числом (воронка 0 основная)."""
    return int(v) if v not in (None, "") else None


def _values(field) -> str:
    return json.dumps([x["VALUE"] for x in (field or []) if x.get("VALUE")], ensure_ascii=False)


MAX_ROWS = 2_000_000


class CursorStuck(bx.BitrixError):
    """Bitrix проигнорировал фильтр >ID или сортировку: курсорная выгрузка невозможна."""


def iter_list(method: str, select: list[str], flt: dict | None = None,
              max_rows: int = MAX_ROWS):
    """Читает все записи метода *.list курсором по ID. Только чтение."""
    if not method.endswith(".list"):
        raise ValueError(f"Экспорт умеет только читать (*.list), получено: {method}")
    if "ID" not in select:
        raise ValueError("select должен содержать ID: по нему идёт курсор")

    last_id, n = 0, 0
    while True:
        data = bx._call_bitrix(method, {
            "filter": {**(flt or {}), ">ID": last_id},
            "select": select, "order": {"ID": "ASC"}, "start": -1})
        rows = data.get("result", [])
        if not rows:
            return

        ids = [int(r["ID"]) for r in rows]
        # 1) страница продвинулась; 2) внутри страницы ID строго возрастают
        if ids[0] <= last_id or any(a >= b for a, b in zip(ids, ids[1:])):
            raise CursorStuck(f"{method}: курсор по ID не работает "
                              f"(после ID {last_id} пришли {ids[:3]}...)")

        yield from rows
        n += len(rows)
        if n > max_rows:  # 3) потолок
            raise bx.BitrixError(f"{method}: больше {max_rows} записей, остановка по лимиту")
        if (n - len(rows)) // 1000 != n // 1000:
            log.info("%s: выгружено ~%d", method, n)
        last_id = ids[-1]


def iter_list_offset(method: str, select: list[str], flt: dict | None = None, start: int = 0):
    """Запасной вариант: обычная пагинация start/next."""
    if not method.endswith(".list"):
        raise ValueError(f"Экспорт умеет только читать (*.list), получено: {method}")
    while True:
        data = bx._call_bitrix(method, {"filter": flt or {}, "select": select,
                                        "order": {"ID": "ASC"}, "start": start})
        yield from data.get("result", [])
        if "next" not in data:
            return
        start = data["next"]


def iter_all(method: str, select: list[str], flt: dict | None = None):
    """Курсор по ID; если Bitrix его не поддерживает, продолжаем обычной пагинацией."""
    seen = 0
    try:
        for row in iter_list(method, select, flt):
            seen += 1
            yield row
    except CursorStuck as e:
        log.warning("%s; переключаюсь на постраничную выгрузку с позиции %d", e, seen)
        yield from iter_list_offset(method, select, flt, start=seen)


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


def export_all(activity_days: int | None = None, db_path: str | None = None) -> None:
    cfg = AuditConfig()
    activity_days = activity_days or cfg.export_days
    db = connect(db_path)
    since = (datetime.now(timezone.utc) - timedelta(days=activity_days)).strftime("%Y-%m-%dT%H:%M:%S")

    with db:  # одна транзакция: при ошибке остаётся предыдущий снимок
        for table in ("users", "companies", "contacts", "deals", "activities"):
            db.execute(f"DELETE FROM {table}")

        try:
            _export_users(db)
        except bx.BitrixError as e:
            log.warning("user.get недоступен (%s), в отчёте будут ID вместо имён", e)

        company_select = ["ID", "TITLE", "ASSIGNED_BY_ID", "DATE_CREATE", "DATE_MODIFY", "EMAIL", "PHONE"]
        if cfg.return_date_field:
            company_select.append(cfg.return_date_field)
        for r in iter_all("crm.company.list", company_select):
            db.execute("INSERT INTO companies VALUES (?,?,?,?,?,?,?,?)", (
                int(r["ID"]), r.get("TITLE"), _int(r.get("ASSIGNED_BY_ID")),
                _utc(r.get("DATE_CREATE")), _utc(r.get("DATE_MODIFY")),
                _values(r.get("EMAIL")), _values(r.get("PHONE")),
                _day(r.get(cfg.return_date_field)) if cfg.return_date_field else None))


        for r in iter_all("crm.contact.list",
                           ["ID", "NAME", "LAST_NAME", "POST", "COMPANY_ID", "ASSIGNED_BY_ID", "EMAIL"]):
            db.execute("INSERT INTO contacts VALUES (?,?,?,?,?,?)", (
                int(r["ID"]), f'{r.get("NAME") or ""} {r.get("LAST_NAME") or ""}'.strip(),
                r.get("POST"), _int(r.get("COMPANY_ID")), _int(r.get("ASSIGNED_BY_ID")),
                _values(r.get("EMAIL"))))

        for r in iter_all("crm.deal.list",
                           ["ID", "TITLE", "COMPANY_ID", "CONTACT_ID", "ASSIGNED_BY_ID", "STAGE_ID",
                            "STAGE_SEMANTIC_ID", "CLOSED", "CATEGORY_ID", "DATE_CREATE", "DATE_MODIFY"]):
            db.execute("INSERT INTO deals VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
                int(r["ID"]), r.get("TITLE"), _int(r.get("COMPANY_ID")), _int(r.get("CONTACT_ID")),
                _int(r.get("ASSIGNED_BY_ID")), r.get("STAGE_ID"), r.get("STAGE_SEMANTIC_ID"),
                r.get("CLOSED"), _int0(r.get("CATEGORY_ID")),
                _utc(r.get("DATE_CREATE")), _utc(r.get("DATE_MODIFY"))))

        for r in iter_all("crm.activity.list",
                           ["ID", "OWNER_TYPE_ID", "OWNER_ID", "TYPE_ID", "PROVIDER_ID", "DIRECTION",
                            "COMPLETED", "CREATED", "DEADLINE", "SUBJECT"],
                           flt={">=CREATED": since}):
            db.execute("INSERT INTO activities VALUES (?,?,?,NULL,?,?,?,?,?,?,?)", (
                int(r["ID"]), _int(r.get("OWNER_TYPE_ID")), _int(r.get("OWNER_ID")),
                _int(r.get("TYPE_ID")), r.get("PROVIDER_ID"), _int(r.get("DIRECTION")),
                r.get("COMPLETED"), _utc(r.get("CREATED")), _utc(r.get("DEADLINE")),
                r.get("SUBJECT")))


        db.execute(ATTACH_SQL)  # привязываем каждую активность к компании
        db.execute("INSERT OR REPLACE INTO meta VALUES ('exported_at', ?)",
                   (datetime.now(timezone.utc).isoformat(),))
    update_ledger(db)
    log.info("Экспорт завершён, журнал ответственных обновлён")
