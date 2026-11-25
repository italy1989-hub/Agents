import sys
from core import bitrix as bx

MARKER = bx.TEST_MARKER
ENTITIES = [  # (list, delete, поле, где стоит маркер); сделки, затем контакты, затем компании
    ("crm.deal.list", "crm.deal.delete", "TITLE"),
    ("crm.contact.list", "crm.contact.delete", "NAME"),
    ("crm.company.list", "crm.company.delete", "TITLE"),
]

def list_marked(list_method: str, field: str) -> list[dict]:
    found, start = [], 0
    while True:
        data = bx._call_bitrix(list_method, {
            "filter": {f"%{field}": MARKER}, "select": ["ID", field], "start": start})
        found += [r for r in data.get("result", []) if r[field].startswith(MARKER)]
        if "next" not in data:
            return found
        start = data["next"]

if __name__ == "__main__":
    if not bx.TEST_MODE or len(MARKER or "") < 6:
        sys.exit("Отказ: TEST_MODE выключен или маркер подозрительно короткий")
    do_delete = "--yes" in sys.argv
    for list_m, delete_m, field in ENTITIES:
        for r in list_marked(list_m, field):
            print("УДАЛЯЮ" if do_delete else "найдено", delete_m, r["ID"], r[field])
            if do_delete:
                bx._call_bitrix(delete_m, {"id": r["ID"]})
