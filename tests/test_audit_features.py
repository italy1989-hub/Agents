from datetime import date

import pytest
from audit import export
from audit.db import connect
from audit.features import compute_facts
from audit.ledger import update_ledger


@pytest.fixture
def db():
    db = connect(":memory:")
    db.execute("INSERT INTO companies (id, title, manager_id, emails) VALUES "
               "(1,'A',10,'[\"info@a.com\"]'), (2,'B',10,'[]'), "
               "(3,'C',11,'[\"info@c.com\",\"office@c.com\"]')")
    db.execute("INSERT INTO contacts (id, name, post, company_id, manager_id, emails) VALUES "
               "(5,'Иван','Директор',1,10,'[\"ivan@a.com\"]'), (6,'Пётр','',1,11,'[]')")
    db.execute("INSERT INTO deals (id, title, company_id, manager_id, stage_semantic) VALUES "
               "(7,'open',1,10,'P'), (8,'won old',1,12,'S')")
    db.execute("""INSERT INTO activities
        (id, owner_type_id, owner_id, type_id, direction, completed, created, deadline, subject) VALUES
        (100,3,5,4,1,'Y','2026-10-01T00:00:00',NULL,NULL),
        (102,2,7,4,1,'Y','2026-11-10T00:00:00',NULL,NULL),
        (101,4,2,4,2,'Y','2026-10-02T00:00:00',NULL,NULL),
        (104,4,3,2,NULL,'N',NULL,'2026-12-01T00:00:00','Позвонить')""")
    db.execute(export.ATTACH_SQL)
    return db


def test_facts(db):
    f = {x.company_id: x for x in compute_facts(db, date(2026, 11, 25))}
    assert f[1].last_inbound == date(2026, 11, 10)        # общение по контакту и по сделке
    assert f[1].managers == {10, 11}                      # закрытая сделка (12) не считается
    assert f[1].contact_ids == [5, 6] and f[1].deal_ids == [7]
    assert f[2].last_inbound is None and f[2].activities_total == 1
    assert (f[3].next_step, f[3].next_step_deadline) == ("Позвонить", date(2026, 12, 1))
    assert f[3].only_generic_emails is True and f[1].only_generic_emails is False


def test_ledger_records_changes_once(db):
    update_ledger(db, today=date(2026, 11, 27))
    update_ledger(db, today=date(2026, 11, 27))           # повтор в тот же день ничего не меняет
    assert db.execute("SELECT COUNT(*) FROM ownership").fetchone()[0] == 3
    db.execute("UPDATE companies SET manager_id = 11 WHERE id = 1")
    update_ledger(db, today=date(2026, 12, 3))
    rows = db.execute("SELECT manager_id, since FROM ownership "
                      "WHERE company_id = 1 ORDER BY since").fetchall()
    assert [(r["manager_id"], r["since"]) for r in rows] == [(10, "2026-11-27"), (11, "2026-12-03")]
