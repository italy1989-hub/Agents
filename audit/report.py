import csv
import os
from collections import Counter, defaultdict
from datetime import datetime
from urllib.parse import urlparse

from audit.config import AuditConfig
from audit.db import connect
from audit.features import compute_features
from audit.scoring import KEEP, REVIEW, RELEASE, classify
from core import bitrix as bx


def load_protected(path: str = os.getenv("AUDIT_PROTECTED_FILE", "audit/protected.txt")) -> set[int]:
    """Белый список: по одному ID компании в строке, после # комментарий."""
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as fh:
        return {int(l.split("#")[0]) for l in fh if l.split("#")[0].strip()}


def activity_breakdown(db_path: str | None = None) -> list[tuple]:
    """Что за активности лежат в базе: (тип, провайдер, направление, количество)."""
    db = connect(db_path)
    return [tuple(r) for r in db.execute(
        "SELECT type_id, provider_id, direction, COUNT(*) FROM activities "
        "GROUP BY 1, 2, 3 ORDER BY 4 DESC")]


def build_report(cfg: AuditConfig, out_dir: str = "reports", db_path: str | None = None,
                 protected: set[int] | frozenset = frozenset()) -> str:
    db = connect(db_path)
    users = {r["id"]: r["name"] for r in db.execute("SELECT id, name FROM users")}
    rows = [(f, *classify(f, cfg, protected)) for f in compute_features(db, cfg)]

    stats: dict = defaultdict(Counter)
    for f, verdict, _ in rows:
        stats[f.manager_id][verdict] += 1

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"audit_{datetime.now():%Y%m%d_%H%M}.csv")
    u = urlparse(bx.BITRIX_WEBHOOK or "")
    base = f"{u.scheme}://{u.netloc}"
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:  # открывается в Excel
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Менеджер", "ID компании", "Компания", "Вердикт", "Причины", "Открытых сделок",
                    "Входящих", "Исходящих", "Последняя входящая", "Последняя активность", "Ссылка"])
        for f, verdict, reasons in sorted(rows, key=lambda r: (r[0].manager_id or 0, r[1])):
            if verdict == KEEP:
                continue
            w.writerow([users.get(f.manager_id, f"ID {f.manager_id}"), f.company_id, f.title,
                        verdict, "; ".join(reasons), f.open_deals, f.inbound, f.outbound,
                        f.last_inbound or "", f.last_any or "",
                        f"{base}/crm/company/details/{f.company_id}/"])

    lines = [f'{"Менеджер":<28}{"всего":>7}{"KEEP":>7}{"REVIEW":>8}{"RELEASE":>9}']
    for mid, c in sorted(stats.items(), key=lambda kv: -sum(kv[1].values())):
        name = users.get(mid, f"ID {mid}")
        lines.append(f"{name[:27]:<28}{sum(c.values()):>7}{c[KEEP]:>7}{c[REVIEW]:>8}{c[RELEASE]:>9}")

    total = len(rows) or 1
    share = sum(1 for _, v, _ in rows if v == RELEASE) / total
    if share > cfg.max_release_share:
        lines.append(f"\nВНИМАНИЕ: под освобождение попадает {share:.0%} базы "
                     f"(порог {cfg.max_release_share:.0%}). Проверьте пороги и качество выгрузки.")
    lines.append(f"\nCSV: {path}")
    return "\n".join(lines)
