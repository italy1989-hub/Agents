import hashlib
import json
from dataclasses import asdict
from typing import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

import bitrix_client as bx
import store
import tools
from decide import decide


class CardState(TypedDict, total=False):
    image_path: str
    user_bitrix_id: int
    sha: str
    card: dict
    dups: dict
    deals: list
    plan: dict
    created: dict
    stop: str
    report: str


# ---------- вспомогательное ----------

def _extract(image_path: str) -> dict:
    """Единственное место, где участвует LLM."""
    return json.loads(tools.extract_contact_from_image.invoke({"image_path": image_path}))


def describe(plan: dict, card: dict) -> str:
    who = f'{card.get("first_name", "")} {card.get("last_name", "")}'.strip() or "—"
    steps = [name for flag, name in (
        (plan["create_company"], "создать компанию"),
        (plan["create_contact"], "создать контакт"),
        (plan["create_deal"], "создать сделку")) if flag]
    return (f'Визитка: {who}, {card.get("company") or "—"}. '
            f'{plan["reason"]}. Будет выполнено: {", ".join(steps)}.')


# ---------- узлы ----------

def prepare(state: CardState):
    path = tools.safe_card_path(state["image_path"])
    if path is None:
        return {"stop": tools.explain_path_error(state["image_path"])}
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    rec = store.get(sha)
    if rec:
        if rec["status"] == "done":
            return {"stop": f'Эта визитка уже обработана: {rec["ids"]}'}
        return {"stop": f'Прошлая обработка завершилась ошибкой ({rec["ids"]}), нужна ручная проверка'}
    return {"sha": sha, "image_path": str(path)}


def extract(state: CardState):
    card = _extract(state["image_path"])
    if "error" in card:
        return {"stop": f'Распознавание не удалось: {card["error"]}'}
    return {"card": card}


def find_dups(state: CardState):
    c = state["card"]
    d = bx.find_duplicates(c.get("emails", []), c.get("phones", []))
    if d["error"]:
        return {"stop": "Не удалось проверить дубли (ошибка Bitrix). Запись запрещена."}
    if not d["searched"]:
        return {"stop": "На визитке нет телефона и email — нужна ручная проверка."}
    return {"dups": d}


def find_deals(state: CardState):
    d = state["dups"]
    found: dict = {}
    try:
        for cid in d["contacts"]:
            for deal in bx.find_open_deals(contact_id=int(cid)):
                found[deal["ID"]] = deal
        for cid in d["companies"]:
            for deal in bx.find_open_deals(company_id=int(cid)):
                found[deal["ID"]] = deal
    except bx.BitrixError as e:
        return {"stop": f"Не удалось получить сделки: {e}"}
    return {"deals": list(found.values())}


def decide_node(state: CardState):
    plan = decide(state["card"], state["dups"], state["deals"])
    if plan.action == "manual":
        return {"plan": asdict(plan), "stop": plan.reason}
    return {"plan": asdict(plan)}


def approve(state: CardState):
    # ВАЖНО: до interrupt нет побочных эффектов, при возобновлении узел выполняется заново
    ok = interrupt({"summary": describe(state["plan"], state["card"])})
    if not ok:
        return {"stop": "Отклонено пользователем, ничего не создано."}
    return {}


def execute(state: CardState):
    plan, card = state["plan"], state["card"]
    company_id, contact_id = plan["company_id"], plan["contact_id"]
    created: dict = {}
    try:
        if plan["create_company"]:
            company_id = bx.create_company(card)
            created["company_id"] = company_id
        if plan["create_contact"]:
            contact_id = bx.create_contact(card, company_id)
            created["contact_id"] = contact_id
        if plan["create_deal"]:
            created["deal_id"] = bx.create_deal(
                card, company_id, contact_id, state.get("user_bitrix_id"))
    except bx.BitrixError as e:
        store.put(state["sha"], "partial", created)
        return {"created": created,
                "stop": f"Ошибка записи: {e}. Создано до ошибки: {created}. Нужна ручная проверка."}
    store.put(state["sha"], "done", created)
    return {"created": created}


def report(state: CardState):
    if state.get("stop"):
        return {"report": state["stop"]}
    plan, created = state.get("plan", {}), state.get("created", {})
    lines = [plan.get("reason", "")]
    if created:
        lines.append(f"Создано: {created}")
    for d in plan.get("existing_deals", []):
        lines.append(f'Сделка #{d["ID"]} «{d["TITLE"]}», ответственный (ID): {d["ASSIGNED_BY_ID"]}')
    return {"report": "\n".join(l for l in lines if l)}


# ---------- маршрутизация ----------

def _go(next_node: str):
    return lambda s: "report" if s.get("stop") else next_node

def _after_decide(s: CardState) -> str:
    if s.get("stop"):
        return "report"
    return "approve" if s["plan"]["action"] == "execute" else "report"


def build_graph(checkpointer=None):
    g = StateGraph(CardState)
    for name, fn in [("prepare", prepare), ("extract", extract), ("find_dups", find_dups),
                     ("find_deals", find_deals), ("decide", decide_node),
                     ("approve", approve), ("execute", execute), ("report", report)]:
        g.add_node(name, fn)

    g.add_edge(START, "prepare")
    for src, dst in [("prepare", "extract"), ("extract", "find_dups"),
                     ("find_dups", "find_deals"), ("find_deals", "decide"),
                     ("approve", "execute"), ("execute", "report")]:
        g.add_conditional_edges(src, _go(dst), {dst: dst, "report": "report"})
    g.add_conditional_edges("decide", _after_decide, {"approve": "approve", "report": "report"})
    g.add_edge("report", END)
    return g.compile(checkpointer=checkpointer or MemorySaver())
