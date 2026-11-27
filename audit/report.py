import csv
import io
import os
from collections import Counter, defaultdict
from datetime import date

from audit.config import AuditConfig
from audit.db import connect
from audit.features import compute_facts
from audit.rules import ACTIVE, EXPIRED, EXPIRED_PLAN, POOL, REVIEW_STATUSES, evaluate
from core.links import card_url

def activity_breakdown(db_path: str | None = None) -> list[tuple]:
    """Из чего состоит общение в базе: (тип, провайдер, направление, количество)."""
    db = connect(db_path)
    return [tuple(r) for r in db.execute(
        "SELECT type_id, provider_id, direction, COUNT(*) FROM activities "
        "GROUP BY 1, 2, 3 ORDER BY 4 DESC")]

COLUMNS = ["Ответственный", "ID компании", "Компания", "Статус", "Отметки", "Начало отсчёта",
           "Срок до", "Последнее входящее", "Следующий шаг", "Срок шага", "Причины",
           "Карточка компании", "Контакты и сделки"]


def _iso(d) -> str:
    return d.isoformat() if d else ""


def build_rows(db, cfg: AuditConfig, today: date) -> list[dict]:
    users = {r["id"]: r["name"] for r in db.execute("SELECT id, name FROM users")}
    rows = []
    for f in compute_facts(db, today):
        v = evaluate(f, cfg, today)
        others = ([card_url("contact", i) for i in f.contact_ids[:3]]
                  + [card_url("deal", i) for i in f.deal_ids[:3]])
        rows.append({
            "Ответственный": users.get(f.manager_id) or (f"ID {f.manager_id}" if f.manager_id else "не назначен"),
            "ID компании": f.company_id, "Компания": f.title, "Статус": v.status,
            "Отметки": "; ".join(v.flags), "Начало отсчёта": _iso(v.start), "Срок до": _iso(v.end),
            "Последнее входящее": _iso(f.last_inbound), "Следующий шаг": f.next_step or "",
            "Срок шага": _iso(f.next_step_deadline), "Причины": "; ".join(v.reasons),
            "Карточка компании": card_url("company", f.company_id),
            "Контакты и сделки": " ".join(others),
        })
    return rows


def review_rows(rows: list[dict]) -> list[dict]:
    """Список на проверку: истёк срок ИЛИ есть отметка (расхождение, мало данных)."""
    return [r for r in rows if r["Статус"] in REVIEW_STATUSES or r["Отметки"]]


def summarize(rows: list[dict]) -> list[dict]:
    t: dict = defaultdict(Counter)
    for r in rows:
        c = t[r["Ответственный"]]
        c["Всего"] += 1
        c[r["Статус"]] += 1
        if r["Отметки"]:
            c["С отметками"] += 1
    keys = ["Всего", ACTIVE, EXPIRED, EXPIRED_PLAN, POOL, "С отметками"]
    return [{"Ответственный": m, **{k: c[k] for k in keys}}
            for m, c in sorted(t.items(), key=lambda kv: -kv[1]["Всего"])]


def to_csv_bytes(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, delimiter=";")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")  # так русскоязычный Excel открывает без «кракозябр»


def build_report(cfg: AuditConfig, today: date | None = None, out_dir: str = "reports",
                 db_path: str | None = None) -> str:
    today = today or date.today()
    rows = build_rows(connect(db_path), cfg, today)
    review = review_rows(rows)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"audit_{today:%Y%m%d}.csv")
    with open(path, "wb") as fh:
        fh.write(to_csv_bytes(review))

    lines = []
    if cfg.simulate:
        lines.append(f"СИМУЛЯЦИЯ: отсчёт условно начался {cfg.launch_date:%d.%m.%Y}\n")
    head = ["Ответственный", "Всего", "идёт", "истёк", "истёк+шаг", "пул", "отметки"]
    lines.append(f'{head[0]:<28}' + "".join(f"{h:>11}" for h in head[1:]))
    for s in summarize(rows):
        lines.append(f'{s["Ответственный"][:27]:<28}' + "".join(
            f"{s[k]:>11}" for k in ["Всего", ACTIVE, EXPIRED, EXPIRED_PLAN, POOL, "С отметками"]))

    in_scope = [r for r in rows if r["Статус"] != POOL] or [None]
    share = sum(1 for r in rows if r["Статус"] in REVIEW_STATUSES) / len(in_scope)
    if share > cfg.max_review_share:
        lines.append(f"\nВНИМАНИЕ: на проверку попадает {share:.0%} компаний "
                     f"(порог {cfg.max_review_share:.0%}). Проверьте выгрузку и пороги.")
    lines.append(f"\nСписок на проверку: {len(review)} строк, CSV: {path}")
    return "\n".join(lines)
