import logging
import os
import re
import threading
import time
import requests
from dotenv import load_dotenv
from utils import timeit
import pytest
import bitrix_client as bc

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
