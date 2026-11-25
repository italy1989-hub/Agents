from datetime import datetime

import pytest
from audit import export
from audit.config import AuditConfig
from audit.db import connect
from audit.features import compute_features

NOW = datetime(2026, 11, 25, 12, 0, 0)  # UTC

@pytest.fixture
def db():
    db = connect(":memory:")
    db.execute("INSERT INTO companies (id, title, manager_id, emails) VALUES "
               "(1,'A',10,'[\"info@a.com\"]'), (2,'B',10,'[]'), (3,'C',11,'[\"info@c.com\",\"office@c.com\"]')")
    db.execute("INSERT INTO contacts (id, name, post, company_id, manager_id, emails) VALUES "
               "(5,'Иван','Директор',1,10,'[\"ivan@a.com\"]')")
    db.execute("INSERT INTO deals (id, title, company_id, manager_id, stage_semantic, date_modify) VALUES "
               "(7,'d',1,10,'P','2026-11-01T00:00:00')")
    db.execute("""INSERT INTO activities
        (id, owner_type_id, owner_id, type_id, direction, completed, created, deadline) VALUES
        (100,3,5,4,1,'Y','2026-10-01T00:00:00',NULL),   -- входящее контакту компании 1
        (102,2,7,4,1,'Y','2026-11-10T00:00:00',NULL),   -- входящее по сделке компании 1
        (101,4,2,4,2,'Y','2026-10-02T00:00:00',NULL),   -- исходящее компании 2
        (103,4,2,4,1,'Y','2025-01-01T00:00:00',NULL),   -- старое входящее компании 2 (вне окна)
        (104,4,3,2,NULL,'N',NULL,'2026-12-01T00:00:00') -- запланированное дело компании 3
    """)
    db.execute(export.ATTACH_SQL)
    return db

def test_features(db):
    f = {x.company_id: x for x in compute_features(db, AuditConfig(), now=NOW)}
    assert (f[1].open_deals, f[1].inbound, f[1].has_dm) == (1, 2, True)
    assert f[1].last_inbound == "2026-11-10T00:00:00"
    assert f[1].only_generic_emails is False        # у контакта личный адрес
    assert (f[2].inbound, f[2].outbound) == (0, 1)  # старое входящее не считается
    assert f[3].planned == 1
    assert f[3].only_generic_emails is True

def test_activity_attached_via_contact_and_deal(db):
    rows = db.execute("SELECT id, company_id FROM activities WHERE id IN (100, 102)").fetchall()
    assert {r["company_id"] for r in rows} == {1}

def test_iter_list_paginates_by_id(monkeypatch):
    pages = [[{"ID": "1"}, {"ID": "2"}], [{"ID": "3"}], []]
    seen = []
    def fake(method, params):
        seen.append(params["filter"][">ID"])
        return {"result": pages.pop(0)}
    monkeypatch.setattr(export.bx, "_call_bitrix", fake)
    assert [r["ID"] for r in export.iter_list("crm.company.list", ["ID"])] == ["1", "2", "3"]
    assert seen == [0, 2, 3]

def test_iter_list_refuses_non_list_methods():
    with pytest.raises(ValueError):
        list(export.iter_list("crm.company.delete", []))

def test_utc_normalization():
    assert export._utc("2026-11-25T15:30:00+03:00") == "2026-11-25T12:30:00"
    assert export._utc(None) is None
