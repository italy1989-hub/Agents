from datetime import date

from audit.config import AuditConfig
from audit.features import CompanyFacts
from audit import rules
from audit.rules import ACTIVE, EXPIRED, EXPIRED_PLAN, POOL

CFG = AuditConfig(pool_user_id=99, launch_date=date(2026, 12, 1))

def F(**kw):
    return CompanyFacts(**{"company_id": 1, "title": "X", "manager_id": 10, "managers": {10},
                           "cards": 1, "activities_total": 1, **kw})

def verdict(f, today, cfg=CFG):
    return rules.evaluate(f, cfg, today)

def test_term_end_variants():
    s = date(2026, 12, 1)
    assert rules.term_end(s, None, None, 20) == date(2026, 12, 21)
    assert rules.term_end(s, date(2026, 12, 10), None, 20) == date(2026, 12, 30)
    assert rules.term_end(s, date(2026, 11, 25), None, 20) == date(2026, 12, 21)   # до старта не считается
    assert rules.term_end(s, None, date(2027, 1, 15), 20) == date(2027, 1, 15)     # «вернуться в дату»

def test_pool_is_skipped():
    assert verdict(F(manager_id=99), date(2027, 1, 1)).status == POOL

def test_boundary_of_term():
    assert verdict(F(), date(2026, 12, 21)).status == ACTIVE
    assert verdict(F(), date(2026, 12, 22)).status == EXPIRED

def test_assigned_before_launch_starts_on_launch():
    assert verdict(F(assigned_since=date(2026, 11, 20)), date(2026, 12, 21)).status == ACTIVE

def test_new_assignment_starts_on_assignment_date():
    f = F(assigned_since=date(2026, 12, 10))
    assert verdict(f, date(2026, 12, 25)).status == ACTIVE
    assert verdict(f, date(2026, 12, 31)).status == EXPIRED

def test_inbound_after_start_renews():
    f = F(last_inbound=date(2026, 12, 10))
    assert verdict(f, date(2026, 12, 28)).status == ACTIVE
    assert verdict(f, date(2026, 12, 31)).status == EXPIRED

def test_inbound_before_launch_does_not_renew():
    assert verdict(F(last_inbound=date(2026, 11, 25)), date(2026, 12, 22)).status == EXPIRED

def test_planned_step_changes_status_not_term():
    f = F(next_step="Позвонить", next_step_deadline=date(2027, 1, 5))
    assert verdict(f, date(2026, 12, 25)).status == EXPIRED_PLAN

def test_mismatch_is_a_separate_flag():
    v = verdict(F(managers={10, 11}), date(2026, 12, 5))
    assert v.status == ACTIVE and rules.FLAG_MISMATCH in v.flags

def test_not_enough_data_flag():
    assert rules.FLAG_NO_DATA in verdict(F(manager_id=None, managers=set()), date(2026, 12, 5)).flags
    assert rules.FLAG_NO_DATA in verdict(F(cards=0, activities_total=0), date(2026, 12, 5)).flags

def test_simulation_ignores_ledger():
    cfg = AuditConfig(simulate=True, launch_date=date(2026, 12, 1))
    f = F(assigned_since=date(2026, 12, 20))
    assert verdict(f, date(2026, 12, 22), cfg).status == EXPIRED
