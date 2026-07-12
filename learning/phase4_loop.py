from typing import TypedDict, Annotated
import operator
from tools import fetch_logs, get_deploy_history
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, START, END

class IncidentState(TypedDict):
    incident: str
    service: str
    plan: str
    evidence: Annotated[list, operator.add]
    hypothesis: str
    enough_evidence: str
    iterations: int

def act_node(state: IncidentState) -> IncidentState:
    already_checked = [item["tool"] for item in state["evidence"]]
    prompt = f"""You are investigating this incident: {state['incident']}

    Tools already used: {already_checked if already_checked else "none yet"}

    Available tools:
    - fetch_logs: get recent log lines for the service
    - get_deploy_history: get recent deployments for the service

    Which tool should be used next to investigate further? If a tool was already used and you want different information, prefer a tool not yet used.
    Answer with exactly one word: fetch_logs or get_deploy_history"""
    
    response = llm.invoke(prompt)
    choice = response.content.strip().lower()

    print(f"act_node: LLM chose '{choice}' (already checked: {already_checked})")

    service = state["service"]
    if "deploy" in choice:
        result = get_deploy_history(service)
        tool_used = "get_deploy_history"
    else:
        result = fetch_logs(service)
        tool_used = "fetch_logs"

    return {"evidence": [{"tool": tool_used, "result": result}]}

llm = ChatOllama(model = "llama3.1:8b", temperature=0)

def plan_node(state: IncidentState) -> IncidentState:
    prompt = f"""You are an on-call engineer investigating a production incident.

    Incident: {state['incident']}

    In 2-3 sentences, describe what you would investigate first and why."""
    response = llm.invoke(prompt)
    return {"plan": response.content}

def reason_node(state: IncidentState) -> IncidentState:
    evidence_text = ""
    for item in state["evidence"]:
        evidence_text += f"\n From {item['tool']}: {item['result']}\n"

    prompt = f"""You are investigating this incident: {state['incident']}

    Evidence gathered so far:
    {evidence_text}

    Based on this evidence, answer two things:
    1. What is your best hypothesis for the root cause? (1-2 sentences)
    2. Do you have enough evidence to be confident in this hypothesis? Answer exactly "yes" or "no" on its own line.

    Format your answer exactly like this:
    HYPOTHESIS: <your hypothesis>
    ENOUGH: <yes or no>"""

    response = llm.invoke(prompt)
    text = response.content

    print("reason_node raw LLM output: \n", text)

    hypothesis = ""
    enough = "no"

    for line in text.split("\n"):
        if line.startswith("HYPOTHESIS: "):
            hypothesis = line.replace("HYPOTHESIS:", "").strip()
        if line.startswith("ENOUGH:"):
            enough = line.replace("ENOUGH:", "").strip().lower()
    
    return {
        "hypothesis": hypothesis,
        "enough_evidence": enough,
        "iterations": state["iterations"] + 1
    }

def route_after_reason(state: IncidentState) -> str:
    if state["enough_evidence"] == "yes":
        return "done"
    if state["iterations"] >= 3:
        print("Hit iteration cap, stopping even without 'yes'")
        return "done"
    return "act"

builder = StateGraph(IncidentState)
builder.add_node("plan", plan_node)
builder.add_node("act", act_node)
builder.add_node("reason", reason_node)

builder.add_edge(START, "plan")
builder.add_edge("plan", "act")
builder.add_edge("act", "reason")

builder.add_conditional_edges(
    "reason",
    route_after_reason,
    {"act" : "act", "done":END}
)

graph = builder.compile()

if __name__ == "__main__":
    result = graph.invoke({
        "incident": "Checkout service error rate jumped from 0.1% to 12% at 14:32 UTC.",
        "service": "checkout",
        "plan": "",
        "evidence": [],
        "hypothesis": "",
        "enough_evidence": "",
        "iterations": 0
    })

    print("\n--- Final Hypothesis ---")
    print(result["hypothesis"])
    print("\n--- Iterations used ---")
    print(result["iterations"])
    print("\n--- Evidence count ---")
    print(len(result["evidence"]))