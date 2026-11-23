from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import HumanMessage, SystemMessage
from llm_factory import get_llm
from tools import extract_contact_from_image, find_bitrix_duplicates, create_bitrix_company, create_bitrix_contact, create_bitrix_deal

# Состояние графа
class State(TypedDict):
    messages: Annotated[list, add_messages]

tools = [extract_contact_from_image, find_bitrix_duplicates, create_bitrix_company, create_bitrix_contact, create_bitrix_deal]

def agent_node(state: State):
    llm = get_llm()
    llm_with_tools = llm.bind_tools(tools)
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}

# Строим граф
graph_builder = StateGraph(State)
graph_builder.add_node("agent", agent_node)
graph_builder.add_node("tools", ToolNode(tools))

graph_builder.add_edge(START, "agent")
graph_builder.add_conditional_edges("agent", tools_condition)
graph_builder.add_edge("tools", "agent")

graph = graph_builder.compile()
