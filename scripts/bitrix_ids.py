import sys

from core import bitrix as bx


def call(method, params=None):
    try:
        return bx._call_bitrix(method, params or {}).get("result")
    except bx.BitrixError as e:
        print(f"  не удалось ({method}): {e}")
        return None


print("== Воронки сделок ==")
cats = call("crm.category.list", {"entityTypeId": 2})
cats = cats.get("categories", []) if isinstance(cats, dict) else (cats or [])
for c in cats:
    print(f'  воронка ID={c.get("id")}  {c.get("name")}')
    entity = "DEAL_STAGE" if str(c.get("id")) == "0" else f'DEAL_STAGE_{c.get("id")}'
    for s in call("crm.status.list", {"filter": {"ENTITY_ID": entity}}) or []:
        print(f'      стадия {s.get("STATUS_ID")}  {s.get("NAME")}')

print("\n== Источники ==")
for s in call("crm.status.list", {"filter": {"ENTITY_ID": "SOURCE"}}) or []:
    print(f'  {s.get("STATUS_ID")}  {s.get("NAME")}')

if len(sys.argv) > 1:
    needle = sys.argv[1].lower()
    print(f"\n== Сотрудники, содержащие «{needle}» ==")
    for active in (True, False):
        for u in call("user.get", {"FILTER": {"ACTIVE": active}}) or []:
            name = f'{u.get("NAME", "")} {u.get("LAST_NAME", "")}'.strip()
            if needle in name.lower() or needle in (u.get("EMAIL") or "").lower():
                print(f'  ID={u.get("ID")}  {name}  (активен: {active})')
