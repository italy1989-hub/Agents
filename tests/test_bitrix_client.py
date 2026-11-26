import logging
import os
import re
import threading
import time
import requests
from dotenv import load_dotenv
import pytest
from core import bitrix as bc

def test_normalize_phone():
    assert bc.normalize_phone("8 (999) 111-22-33") == "+79991112233"
    assert bc.normalize_phone("+7 999 111 22 33") == "+79991112233"
    assert bc.normalize_phone("") is None

def test_split_name_russian_order():
    assert bc.split_name("Иванов Иван Иванович") == ("Иван", "Иванов", "Иванович")

def test_empty_input_does_not_call_api(monkeypatch):
    calls = []
    monkeypatch.setattr(bc, "_call_bitrix", lambda m, p: calls.append(m) or {})
    r = bc.find_duplicates([], [""])
    assert calls == [] and r["searched"] is False

def test_api_error_sets_flag(monkeypatch):
    def boom(m, p): raise bc.BitrixError("QUERY_LIMIT_EXCEEDED")
    monkeypatch.setattr(bc, "_call_bitrix", boom)
    assert bc.find_duplicates(["a@b.com"], [])["error"] is True

def test_bitrix_200_with_error(monkeypatch):
    class R:
        status_code = 200
        def json(self): return {"error": "ACCESS_DENIED", "error_description": "no"}
        def raise_for_status(self): pass
    monkeypatch.setattr(bc, "BITRIX_WEBHOOK", "https://x/rest/1/k/")
    monkeypatch.setattr(bc.requests, "post", lambda *a, **k: R())
    with pytest.raises(bc.BitrixError):
        bc._call_bitrix("crm.contact.list", {})

@pytest.fixture
def captured(monkeypatch):
    """Подменяет _call_bitrix и запоминает (метод, параметры)."""
    calls = []
    def fake(method, params):
        calls.append((method, params))
        return {"result": 42}
    monkeypatch.setattr(bc, "_call_bitrix", fake)
    monkeypatch.setattr(bc, "TEST_MODE", False)
    return calls

def test_create_contact_uses_name_fields(captured):
    bc.create_contact({"first_name": "Иван", "last_name": "Иванов",
                       "second_name": "Иванович", "phones": ["+79991112233"]}, company_id=7)
    method, p = captured[0]
    f = p["fields"]
    assert method == "crm.contact.add"
    assert (f["NAME"], f["LAST_NAME"], f["SECOND_NAME"]) == ("Иван", "Иванов", "Иванович")
    assert f["COMPANY_ID"] == 7
    assert f["PHONE"] == [{"VALUE": "+79991112233", "VALUE_TYPE": "WORK"}]

def test_create_contact_fallback_to_full_name(captured):
    bc.create_contact({"contact_name": "Иванов Иван Иванович"})
    f = captured[0][1]["fields"]
    assert (f["NAME"], f["LAST_NAME"]) == ("Иван", "Иванов")

def test_create_contact_without_company(captured):
    bc.create_contact({"first_name": "Иван"})
    assert "COMPANY_ID" not in captured[0][1]["fields"]

def test_test_marker_added_in_test_mode(captured, monkeypatch):
    monkeypatch.setattr(bc, "TEST_MODE", True)
    monkeypatch.setattr(bc, "TEST_MARKER", "[@TEST@]")
    bc.create_company({"company": "Ромашка"})
    assert captured[0][1]["fields"]["TITLE"].startswith("[@TEST@]")

def test_no_marker_in_prod_mode(captured):
    bc.create_company({"company": "Ромашка"})
    assert captured[0][1]["fields"]["TITLE"] == "Ромашка"

def test_create_deal_links_and_assignee(captured):
    bc.create_deal({"company": "Ромашка"}, company_id=7, contact_id=8, assigned_by_id=15)
    f = captured[0][1]["fields"]
    assert (f["COMPANY_ID"], f["CONTACT_ID"], f["ASSIGNED_BY_ID"]) == (7, 8, 15)

def test_create_deal_without_assignee(captured):
    bc.create_deal({"company": "Ромашка"})
    assert "ASSIGNED_BY_ID" not in captured[0][1]["fields"]

def test_find_open_deals_prefers_contact(captured):
    bc.find_open_deals(company_id=7, contact_id=8)
    method, p = captured[0]
    assert method == "crm.deal.list"
    assert p["filter"] == {"CONTACT_ID": 8, "CLOSED": "N"}

def test_find_open_deals_nothing_to_search(captured):
    assert bc.find_open_deals() == [] and captured == []

def test_extract_ids_handles_all_shapes():
    assert bc._extract_ids({"result": {"CONTACT": [1, 2]}}, "CONTACT") == [1, 2]
    assert bc._extract_ids({"result": [3]}, "CONTACT") == [3]
    assert bc._extract_ids({"result": []}, "CONTACT") == []
    assert bc._extract_ids({}, "CONTACT") == []

def test_duplicates_are_merged_and_deduped(monkeypatch):
    def fake(method, params):
        return {"result": {params["entity_type"]: [1, 2] if params["type"] == "EMAIL" else [2, 3]}}
    monkeypatch.setattr(bc, "_call_bitrix", fake)
    r = bc.find_duplicates(["a@b.ru"], ["+79991112233"])
    assert r["contacts"] == [1, 2, 3] and r["error"] is False

def _wh(monkeypatch):
    monkeypatch.setattr(bc, "BITRIX_WEBHOOK", "https://x/rest/1/k/")
    monkeypatch.setattr(bc.time, "sleep", lambda s: None)

def test_write_read_timeout_not_retried(monkeypatch):
    _wh(monkeypatch)
    n = []
    def post(*a, **k): n.append(1); raise requests.ReadTimeout("slow")
    monkeypatch.setattr(bc.requests, "post", post)
    with pytest.raises(bc.BitrixTimeout):
        bc._call_bitrix("crm.company.add", {})
    assert len(n) == 1

def test_connect_timeout_is_retried_even_for_write(monkeypatch):
    _wh(monkeypatch)
    class R:
        status_code = 200
        def json(self): return {"result": 5}
        def raise_for_status(self): pass
    seq = [requests.ConnectTimeout("x"), requests.ConnectTimeout("x"), R()]
    def post(*a, **k):
        v = seq.pop(0)
        if isinstance(v, Exception): raise v
        return v
    monkeypatch.setattr(bc.requests, "post", post)
    assert bc._call_bitrix("crm.company.add", {})["result"] == 5

def _timeout_then_list(result):
    def fake(method, params):
        if method.endswith(".add"):
            raise bc.BitrixTimeout("t")
        return {"result": result}
    return fake

def test_timeout_then_record_found_returns_its_id(monkeypatch):
    _wh(monkeypatch); monkeypatch.setattr(bc, "TEST_MODE", False)
    monkeypatch.setattr(bc, "_call_bitrix", _timeout_then_list([{"ID": "77"}]))
    assert bc.create_company({"company": "X"}) == 77

@pytest.mark.parametrize("found", [[], [{"ID": "1"}, {"ID": "2"}]])
def test_timeout_then_zero_or_many_raises(monkeypatch, found):
    _wh(monkeypatch); monkeypatch.setattr(bc, "TEST_MODE", False)
    monkeypatch.setattr(bc, "_call_bitrix", _timeout_then_list(found))
    with pytest.raises(bc.BitrixTimeout):
        bc.create_company({"company": "X"})

def test_assignee_on_company_and_contact(captured):
    bc.create_company({"company": "X"}, assigned_by_id=15)
    bc.create_contact({"first_name": "Иван"}, assigned_by_id=15)
    assert captured[0][1]["fields"]["ASSIGNED_BY_ID"] == 15
    assert captured[1][1]["fields"]["ASSIGNED_BY_ID"] == 15

def test_phone_extension_is_dropped():
    assert bc.normalize_phone("+52 (442) 103-0500 x 1277") == "+524421030500"
    assert bc.normalize_phone("8 (999) 111-22-33 доб. 45") == "+79991112233"

def test_deal_funnel_and_source_from_env(captured, monkeypatch):
    monkeypatch.setenv("BITRIX_DEAL_CATEGORY_ID", "5")
    monkeypatch.setenv("BITRIX_DEAL_STAGE_ID", "C5:NEW")
    monkeypatch.setenv("BITRIX_SOURCE_ID", "VISITKA")
    bc.create_deal({"company": "X"})
    f = captured[0][1]["fields"]
    assert (f["CATEGORY_ID"], f["STAGE_ID"], f["SOURCE_ID"]) == (5, "C5:NEW", "VISITKA")
