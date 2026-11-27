import sys

import app


def _run(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["app", *argv])
    app.main()


def test_export_runs_export_and_not_report(monkeypatch):
    calls = []
    monkeypatch.setattr("audit.export.export_all", lambda days=None: calls.append(days))

    def boom(*a, **k):
        raise AssertionError("отчёт не должен строиться при export")
    monkeypatch.setattr("audit.report.build_report", boom)
    _run(monkeypatch, "audit", "export", "--activity-days", "7")
    assert calls == [7]


def test_report_runs_report_and_not_export(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("выгрузка не должна запускаться при report")
    monkeypatch.setattr("audit.export.export_all", boom)
    monkeypatch.setattr("audit.report.build_report", lambda cfg: "ok")
    _run(monkeypatch, "audit", "report", "--simulate-days", "25")
