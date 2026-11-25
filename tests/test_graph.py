import pytest
from langgraph.types import Command

from cards import graph as g
from core import store
from cards import tools


@pytest.fixture
def env(tmp_path, monkeypatch):
    cards = tmp_path / "cards"; cards.mkdir()
    img = cards / "c.jpg"; img.write_bytes(b"fake-image")
    monkeypatch.setattr(tools, "ALLOWED_DIR", cards.resolve())
    monkeypatch.setattr(store, "DB_PATH", str(tmp_path / "s.db"))
    monkeypatch.setattr(g, "_extract", lambda p: {
        "company": "Ромашка", "first_name": "Иван", "last_name": "Иванов",
        "phones": ["+79991112233"], "emails": ["a@b.ru"]})
    calls = []
    monkeypatch.setattr(g.bx, "find_duplicates",
        lambda e, p: {"contacts": [], "companies": [], "error": False, "searched": True})
    monkeypatch.setattr(g.bx, "create_company", lambda c: calls.append("company") or 1)
    monkeypatch.setattr(g.bx, "create_contact", lambda c, cid=None: calls.append("contact") or 2)
    monkeypatch.setattr(g.bx, "create_deal",
        lambda c, co=None, ct=None, a=None: calls.append(("deal", co, ct, a)) or 3)
    return img, calls

def run(graph, img, answers=()):
    cfg = {"configurable": {"thread_id": "t"}}
    out = graph.invoke({"image_path": str(img), "user_bitrix_id": 15}, cfg)
    for a in answers:
        assert out.get("__interrupt__"), "ожидался вопрос пользователю"
        out = graph.invoke(Command(resume=a), cfg)
    return out

def test_full_flow_two_questions(env):
    img, calls = env
    out = run(g.build_graph(), img, answers=[True, True])
    assert calls == ["company", "contact", ("deal", 1, 2, 15)]
    assert out["created"] == {"company_id": 1, "contact_id": 2, "deal_id": 3}

def test_decline_entities_creates_nothing(env):
    img, calls = env
    out = run(g.build_graph(), img, answers=[False])
    assert calls == [] and "Отклонено" in out["report"]

def test_entities_yes_deal_no(env):
    img, calls = env
    out = run(g.build_graph(), img, answers=[True, False])
    assert calls == ["company", "contact"] and "Сделка не создана" in out["report"]
    import hashlib
    sha = hashlib.sha256(img.read_bytes()).hexdigest()
    assert store.get(sha)["status"] == "entities_done"

def test_declined_deal_can_be_offered_again(env):
    img, calls = env
    run(g.build_graph(), img, answers=[True, False])
    out = g.build_graph().invoke({"image_path": str(img)}, {"configurable": {"thread_id": "t2"}})
    assert out.get("__interrupt__")          # не заблокировано как «уже обработана»

def test_nothing_written_before_approval(env):
    img, calls = env
    assert run(g.build_graph(), img).get("__interrupt__") and calls == []

def test_existing_contact_asks_only_about_deal(env, monkeypatch):
    img, calls = env
    monkeypatch.setattr(g.bx, "find_duplicates",
        lambda e, p: {"contacts": [5], "companies": [], "error": False, "searched": True})
    monkeypatch.setattr(g.bx, "find_open_deals", lambda **k: [])
    out = run(g.build_graph(), img, answers=[True])      # один вопрос, не два
    assert calls == [("deal", None, 5, 15)] and not out.get("__interrupt__")

def test_error_on_deal_keeps_entities_in_partial(env, monkeypatch):
    img, calls = env
    def boom(*a, **k): raise g.bx.BitrixError("ACCESS_DENIED")
    monkeypatch.setattr(g.bx, "create_deal", boom)
    out = run(g.build_graph(), img, answers=[True, True])
    assert "ACCESS_DENIED" in out["report"] and "company_id" in out["report"]


def test_bitrix_error_on_search_blocks_everything(env, monkeypatch):
    img, calls = env
    monkeypatch.setattr(g.bx, "find_duplicates",
        lambda e, p: {"contacts": [], "companies": [], "error": True, "searched": True})
    out = run(g.build_graph(), img)
    assert calls == [] and "Запись запрещена" in out["report"]

