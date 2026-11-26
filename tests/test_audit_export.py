import pytest
from audit import export


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


def test_day_keeps_date_without_timezone_shift():
    assert export._day("2026-12-15T00:00:00+03:00") == "2026-12-15"
    assert export._day(None) is None

def test_iter_list_detects_filter_ignored(monkeypatch):
    # Bitrix каждый раз отдаёт одну и ту же страницу
    monkeypatch.setattr(export.bx, "_call_bitrix",
                        lambda m, p: {"result": [{"ID": "1"}, {"ID": "2"}]})
    got = []
    with pytest.raises(export.CursorStuck):
        for r in export.iter_list("crm.activity.list", ["ID"]):
            got.append(r["ID"])
    assert got == ["1", "2"]          # дубль второй страницы в выдачу не попал


def test_iter_list_detects_ignored_sort(monkeypatch):
    # страница пришла не по порядку: брать последний ID как курсор нельзя
    monkeypatch.setattr(export.bx, "_call_bitrix",
                        lambda m, p: {"result": [{"ID": "5"}, {"ID": "3"}]})
    with pytest.raises(export.CursorStuck):
        list(export.iter_list("crm.activity.list", ["ID"]))


def test_iter_list_row_limit(monkeypatch):
    n = iter(range(1, 10_000))
    monkeypatch.setattr(export.bx, "_call_bitrix",
                        lambda m, p: {"result": [{"ID": str(next(n))}]})
    with pytest.raises(export.bx.BitrixError, match="лимиту"):
        list(export.iter_list("crm.activity.list", ["ID"], max_rows=5))


def test_iter_list_requires_id_in_select():
    with pytest.raises(ValueError):
        list(export.iter_list("crm.company.list", ["TITLE"]))


def test_iter_all_falls_back_to_offset_without_duplicates(monkeypatch):
    def fake(method, params):
        if params["start"] == -1:                 # курсорный режим: всегда одна и та же страница
            return {"result": [{"ID": "1"}, {"ID": "2"}]}
        assert params["start"] == 2               # продолжаем ровно с того места, где остановились
        return {"result": [{"ID": "3"}]}          # без "next": конец
    monkeypatch.setattr(export.bx, "_call_bitrix", fake)
    assert [r["ID"] for r in export.iter_all("crm.activity.list", ["ID"])] == ["1", "2", "3"]
