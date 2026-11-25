import pytest
from audit.config import AuditConfig
from audit.features import Features
from audit.scoring import KEEP, REVIEW, RELEASE, classify

CFG = AuditConfig()

def F(**kw):
    return Features(**{"company_id": 1, "title": "X", "manager_id": 3, **kw})

def test_open_deal_with_inbound_is_kept():
    assert classify(F(open_deals=1, inbound=2, has_dm=True), CFG)[0] == KEEP

def test_recent_won_deal_protects():
    assert classify(F(recent_won=1), CFG)[0] == KEEP

def test_planned_activity_protects():
    assert classify(F(planned=1), CFG)[0] == KEEP

def test_whitelist_beats_everything():
    assert classify(F(), CFG, protected={1}) == (KEEP, ["в белом списке"])

def test_nothing_at_all_is_released():
    verdict, reasons = classify(F(), CFG)
    assert verdict == RELEASE and "нет открытых сделок" in reasons

def test_only_outbound_is_released_and_explained():
    verdict, reasons = classify(F(outbound=10), CFG)
    assert verdict == RELEASE and any("только исходящие" in r for r in reasons)

def test_generic_email_noted():
    assert any("общие адреса" in r for r in classify(F(only_generic_emails=True), CFG)[1])

def test_open_deal_without_inbound_goes_to_review():
    verdict, reasons = classify(F(open_deals=1, outbound=5), CFG)
    assert verdict == REVIEW and any("не отвечал" in r for r in reasons)

def test_inbound_without_deal_goes_to_review():
    assert classify(F(inbound=1), CFG)[0] == REVIEW

def test_require_dm_changes_keep_to_review():
    f = F(open_deals=1, inbound=1, has_dm=False)
    assert classify(f, AuditConfig(require_dm=True))[0] == REVIEW
    assert classify(f, AuditConfig(require_dm=False))[0] == KEEP
