import os
import argparse
import logging
from datetime import date, timedelta


def main():
    p = argparse.ArgumentParser(prog="app")
    sub = p.add_subparsers(dest="task", required=True)

    c = sub.add_parser("cards", help="Задача 1: визитка в CRM")
    c.add_argument("image")
    c.add_argument("--user", type=int, help="Bitrix ID сканирующего")

    a = sub.add_parser("audit", help="Задача 2: аудит базы (только чтение)")
    a.add_argument("action", choices=["export", "stats", "report"])
    a.add_argument("--activity-days", type=int, default=None,
                   help="за сколько дней выгружать активности")
    a.add_argument("--simulate-days", type=int,
                   help="симуляция: отсчёт начался N дней назад")

    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("urllib3").setLevel(logging.WARNING)   # urllib3 печатает полный адрес вебхука, то есть ключ
    if os.getenv("LOG_TIMING"):
        logging.getLogger("timing").setLevel(logging.DEBUG)  # замеры времени, по желанию

    if args.task == "cards":
        from cards.service import process_card
        print(process_card(
            args.image, args.user,
            ask=lambda s: input(f"\n{s}\nПодтвердить? (y/n): ").strip().lower() == "y"))
        return

    if args.action == "export":
        from audit.export import export_all
        export_all(args.activity_days)
    elif args.action == "stats":
        from audit.report import activity_breakdown
        for row in activity_breakdown():
            print(row)
    else:
        from audit.config import AuditConfig
        from audit.report import build_report
        cfg = AuditConfig()
        if args.simulate_days:
            cfg.simulate = True
            cfg.launch_date = date.today() - timedelta(days=args.simulate_days)
        print(build_report(cfg))


if __name__ == "__main__":
    main()
