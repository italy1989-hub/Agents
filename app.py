import argparse
import logging


def main():
    p = argparse.ArgumentParser(prog="app")
    sub = p.add_subparsers(dest="task", required=True)

    c = sub.add_parser("cards", help="Задача 1: визитка в CRM")
    c.add_argument("image")
    c.add_argument("--user", type=int, help="Bitrix ID сканирующего")

    a = sub.add_parser("audit", help="Задача 2: аудит базы (только чтение)")
    a.add_argument("action", choices=["export", "stats", "report"])
    a.add_argument("--window", type=int, default=180, help="окно поиска коммуникации, дней")
    a.add_argument("--activity-days", type=int, default=365, help="за сколько дней выгружать активности")

    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    if args.task == "cards":
        from cards.service import process_card
        print(process_card(
            args.image, args.user,
            ask=lambda s: input(f"\n{s}\nПодтвердить? (y/n): ").strip().lower() == "y"))
    else:
        from audit.config import AuditConfig
        if args.action == "export":
            from audit.export import export_all
            export_all(args.activity_days)
        elif args.action == "stats":
            from audit.report import activity_breakdown
            for row in activity_breakdown():
                print(row)
        else:
            from audit.report import build_report, load_protected
            print(build_report(AuditConfig(window_days=args.window), protected=load_protected()))


if __name__ == "__main__":
    main()
