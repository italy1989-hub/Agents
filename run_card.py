import sys
import uuid

from langgraph.types import Command
from graph import build_graph

graph = build_graph()

def process(image_path: str, user_bitrix_id: int | None = None) -> str:
    cfg = {"configurable": {"thread_id": str(uuid.uuid4())}}
    out = graph.invoke({"image_path": image_path, "user_bitrix_id": user_bitrix_id}, cfg)
    if out.get("__interrupt__"):
        summary = out["__interrupt__"][0].value["summary"]
        ok = input(f"\n{summary}\nПодтвердить? (y/n): ").strip().lower() == "y"
        out = graph.invoke(Command(resume=ok), cfg)
    return out["report"]

if __name__ == "__main__":
    print(process(sys.argv[1], user_bitrix_id=int(sys.argv[2]) if len(sys.argv) > 2 else None))
