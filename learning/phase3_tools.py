from typing import TypedDict, Annotated
import operator
from tools import fetch_logs
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, START, END

class IncidentState(TypedDict):
    incident: str
    service: str
    plan: str
    evidence: Annotated[list, operator.add]

def act_node(state: IncidentState) -> IncidentState:
    service = state["service"]
    logs = fetch_logs(service)

    print(f"act_node fetched {len(logs)} log lines for '{service}'")
    return{"evidence": [{"tool": "fetch_logs", "result":logs}]}

llm = ChatOllama(model = "llama3.1:8b", temperature=0)

def plan_node(state: IncidentState) -> IncidentState:
    prompt = f"""You are an on-call engineer investigating a production incident.

    Incident: {state['incident']}

    In 2-3 sentences, describe what you would investigate first and why."""
    response = llm.invoke(prompt)
    return {"plan": response.content}


builder = StateGraph(IncidentState)
builder.add_node("plan", plan_node)
builder.add_node("act", act_node)

builder.add_edge(START, "plan")
builder.add_edge("plan", "act")
builder.add_edge("act", END)

graph = builder.compile()


if __name__ == "__main__":
    result = graph.invoke({
        "incident": "Checkout service error rate jumped from 0.1% to 12% at 14:32 UTC.",
        "service" : "checkout",
        "plan": "",
        "evidence": []
    })

    print("\n--- Plan ---")
    print(result["plan"])

    print("\n--- Evidence ---")
    print(result["evidence"])