import uuid
from typing import Callable

from langgraph.types import Command
from cards.graph import build_graph

_graph = build_graph()

def process_card(image_path: str, user_bitrix_id: int | None,
                 ask: Callable[[str], bool]) -> str:
    cfg = {"configurable": {"thread_id": str(uuid.uuid4())}}
    out = _graph.invoke({"image_path": image_path, "user_bitrix_id": user_bitrix_id}, cfg)
    while out.get("__interrupt__"):
        question = out["__interrupt__"][0].value["summary"]
        out = _graph.invoke(Command(resume=ask(question)), cfg)
    return out["report"]
