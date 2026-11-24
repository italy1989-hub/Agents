import json
from types import SimpleNamespace

import pytest
import tools


# ---------- _parse_card: «грязные» ответы модели ----------

GOOD = '{"company": "Ромашка", "first_name": "Иван", "last_name": "Иванов", "phones": ["+79991112233"], "emails": ["a@b.ru"]}'

@pytest.mark.parametrize("raw", [
    GOOD,
    f"```json\n{GOOD}\n```",
    f"Вот результат:\n{GOOD}\nНадеюсь, помог!",
    f"{GOOD}\n\nПримечание: {{если что-то не так}}",   # скобки после JSON
])
def test_parse_card_wrappers(raw):
    card = tools._parse_card(raw)
    assert card.company == "Ромашка"
    assert card.last_name == "Иванов"
    assert card.phones == ["+79991112233"]

def test_parse_card_missing_fields_get_defaults():
    card = tools._parse_card('{"company": "X"}')
    assert card.first_name == "" and card.phones == [] and card.emails == []

def test_parse_card_null_values():
    card = tools._parse_card('{"company": "X", "position": null, "phones": null}')
    assert card.position == "" and card.phones == []

def test_parse_card_extra_fields_ignored():
    assert tools._parse_card('{"company": "X", "confidence": 0.9}').company == "X"

def test_parse_card_content_blocks_list():
    blocks = [{"type": "text", "text": GOOD}]
    assert tools._parse_card(blocks).company == "Ромашка"

@pytest.mark.parametrize("raw", ["", "нет данных", "[1, 2, 3]", '{"phones": "не список"}'])
def test_parse_card_garbage_raises(raw):
    with pytest.raises((ValueError, tools.ValidationError)):
        tools._parse_card(raw)


# ---------- extract_contact_from_image: путь к файлу ----------

@pytest.fixture
def cards_dir(tmp_path, monkeypatch):
    d = tmp_path / "cards"
    d.mkdir()
    monkeypatch.setattr(tools, "ALLOWED_DIR", d.resolve())
    return d

def _extract(path):
    return json.loads(tools.extract_contact_from_image.invoke({"image_path": str(path)}))

def test_path_outside_allowed_dir_rejected(cards_dir, tmp_path):
    secret = tmp_path / "secret.jpg"
    secret.write_bytes(b"x")
    assert "error" in _extract(secret)

def test_path_traversal_rejected(cards_dir, tmp_path):
    (tmp_path / "secret.jpg").write_bytes(b"x")
    assert "error" in _extract(cards_dir / ".." / "secret.jpg")

def test_symlink_escape_rejected(cards_dir, tmp_path):
    secret = tmp_path / "secret.jpg"
    secret.write_bytes(b"x")
    link = cards_dir / "link.jpg"
    link.symlink_to(secret)
    assert "error" in _extract(link)

def test_wrong_extension_rejected(cards_dir):
    f = cards_dir / "passwords.txt"
    f.write_text("x")
    assert "error" in _extract(f)

def test_missing_file(cards_dir):
    assert "error" in _extract(cards_dir / "nope.jpg")

def test_rejected_path_never_reaches_llm(cards_dir, tmp_path, monkeypatch):
    def boom():
        raise AssertionError("LLM не должна вызываться")
    monkeypatch.setattr(tools, "get_llm", boom)
    (tmp_path / "secret.jpg").write_bytes(b"x")
    assert "error" in _extract(tmp_path / "secret.jpg")

def test_extract_happy_path_with_fake_llm(cards_dir, monkeypatch):
    f = cards_dir / "card.jpg"
    f.write_bytes(b"\xff\xd8fake")
    fake = SimpleNamespace(invoke=lambda msgs: SimpleNamespace(content=f"```json\n{GOOD}\n```"))
    monkeypatch.setattr(tools, "get_llm", lambda: fake)
    data = _extract(f)
    assert data["last_name"] == "Иванов"

def test_extract_unparseable_llm_answer(cards_dir, monkeypatch):
    f = cards_dir / "card.jpg"
    f.write_bytes(b"\xff\xd8fake")
    fake = SimpleNamespace(invoke=lambda msgs: SimpleNamespace(content="не могу прочитать"))
    monkeypatch.setattr(tools, "get_llm", lambda: fake)
    assert "error" in _extract(f)


# ---------- find_bitrix_duplicates ----------

def _dups(payload, monkeypatch, fake_result):
    monkeypatch.setattr(tools, "_find_dups", lambda e, p: fake_result)
    return json.loads(tools.find_bitrix_duplicates.invoke({"contact_json": json.dumps(payload)}))

def test_dups_no_email_no_phone_is_error(monkeypatch):
    r = _dups({"emails": [], "phones": [""]}, monkeypatch,
              {"contacts": [], "companies": [], "error": False, "searched": False})
    assert r["status"] == "error"

def test_dups_network_error_blocks_creation(monkeypatch):
    r = _dups({"emails": ["a@b.ru"]}, monkeypatch,
              {"contacts": [], "companies": [], "error": True, "searched": True})
    assert r["status"] == "error"

def test_dups_found(monkeypatch):
    r = _dups({"emails": ["a@b.ru"]}, monkeypatch,
              {"contacts": [5], "companies": [], "error": False, "searched": True})
    assert r["contacts"] == [5]

def test_dups_invalid_json():
    r = json.loads(tools.find_bitrix_duplicates.invoke({"contact_json": "{не json"}))
    assert "error" in r


# ---------- create_* инструменты не падают на плохом входе ----------

@pytest.mark.parametrize("tool_name,args", [
    ("create_bitrix_company", {"contact_json": "мусор"}),
    ("create_bitrix_contact", {"contact_json": "мусор"}),
    ("create_bitrix_deal",    {"contact_json": "мусор"}),
])
def test_create_tools_bad_json_returns_error(tool_name, args):
    r = json.loads(getattr(tools, tool_name).invoke(args))
    assert r["status"] == "error"

@pytest.mark.parametrize("tool_name", ["create_bitrix_company", "create_bitrix_contact", "create_bitrix_deal"])
def test_create_tools_non_object_json(tool_name):
    r = json.loads(getattr(tools, tool_name).invoke({"contact_json": "[1, 2]"}))
    assert r["status"] == "error"


def test_dups_non_object_json():
    r = json.loads(tools.find_bitrix_duplicates.invoke({"contact_json": "[1, 2]"}))
    assert "error" in r
