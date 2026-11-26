from datetime import date

LEDGER_SQL = """
INSERT OR REPLACE INTO ownership (company_id, manager_id, since)
SELECT c.id, c.manager_id, :today FROM companies c
WHERE c.manager_id IS NOT (
    SELECT o.manager_id FROM ownership o
    WHERE o.company_id = c.id ORDER BY o.since DESC LIMIT 1)
"""


def update_ledger(db, today: date | None = None) -> None:
    """Фиксирует смену ответственного. Вызывается после каждой выгрузки."""
    db.execute(LEDGER_SQL, {"today": (today or date.today()).isoformat()})
    db.commit()
