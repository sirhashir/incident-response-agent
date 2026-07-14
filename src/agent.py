from typing import TypedDict, Annotated
import operator
from tools import fetch_logs, get_deploy_history, query_metrics
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import interrupt
from langgraph.types import Command
from memory import save_incident, recall_similar
import tools

class IncidentState(TypedDict):
    incident: str
    service: str
    plan: str
    evidence: Annotated[list, operator.add]
    hypothesis: str
    enough_evidence: str
    iterations: int
    proposed_action: str
    approved: str
    hypothesis_history: Annotated[list, operator.add]

def act_node(state: IncidentState) -> IncidentState:
    already_checked = [item["tool"] for item in state["evidence"]]
    prompt = f"""You are investigating this incident: {state['incident']}

            Tools already used: {already_checked if already_checked else "none yet"}

            Available tools:
            - fetch_logs: get recent log lines for the service
            - get_deploy_history: get recent deployments for the service
            - query_metrics: get recent CPU, memory, and error rate metrics for the service

            Which tool should be used next to investigate further? If a tool was already used and you want different information, prefer a tool not yet used.
            Answer with exactly one word: fetch_logs, get_deploy_history, or query_metrics"""
        
    response = llm.invoke(prompt)
    choice = response.content.strip().lower()

    print(f"act_node: LLM chose '{choice}' (already checked: {already_checked})")

    service = state["service"]
    all_tools = ["fetch_logs", "get_deploy_history", "query_metrics"]
    unused = [t for t in all_tools if t not in already_checked]

    if "deploy" in choice:
        tool_used = "get_deploy_history"
    elif "metric" in choice:
        tool_used = "query_metrics"
    else:
        tool_used = "fetch_logs"

    if tool_used in already_checked and unused:
        tool_used = unused[0]
        print(f"act_node: LLM repeated '{choice}', overriding to unused tool '{tool_used}'")

    if tool_used == "get_deploy_history":
        result = get_deploy_history(service)
    elif tool_used == "query_metrics":
        result = query_metrics(service)
    else:
        result = fetch_logs(service)

    return {"evidence": [{"tool": tool_used, "result": result}]}

llm = ChatOllama(model = "llama3.1:8b", temperature=0)

def plan_node(state: IncidentState) -> IncidentState:
    past = recall_similar(state["service"])

    if past:
        history_text = "\n,".join([
            f"Past Incident: {p['incident']} | Hypothesis: {p['hypothesis']} | Action: {p['approved']} (approved: {p['approved']})"
            for p in past
        ])
    else:
        history_text = "No past incidents recorded for this service."
    
    prompt = f"""You are an on-call engineer investigating a production incident.

            Incident: {state['incident']}

            Past incidents for this service:
            {history_text}

            In 2-3 sentences, describe what you would investigate first and why. If a past incident looks similar, mention it."""

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
            2. Is this hypothesis well-supported by the evidence you've gathered, such that a competent
            engineer could act on it? Answer "yes" if the evidence reasonably points to this cause,
            even if you can't be 100% certain. Answer "no" only if the evidence is genuinely
            insufficient, contradictory, or you're essentially guessing.

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
        "hypothesis_history": [hypothesis],
        "enough_evidence": enough,
        "iterations": state["iterations"] + 1
    }

def propose_node(state: IncidentState) -> IncidentState:

    if state["enough_evidence"] != "yes":
        action = (
            f"ESCALATE: Insufficient evidence to confidently determine root cause after "
            f"{state['iterations']} investigation attempts. Current best guess: "
            f"{state['hypothesis']}. Recommend manual investigation by an on-call engineer "
            f"before taking any remediation action."
        )
        print(f"propose_node: escalating instead of proposing action (low confidence)")
        return {"proposed_action": action}

    prompt = f"""You are an on-call engineer. Based on this hypothesis about a production incident, propose ONE concrete remediation action.

    Hypothesis: {state['hypothesis']}

    Answer in one sentence, describing exactly what action to take (e.g. "restart the payment-gateway service" or "roll back the last deployment to payment-gateway")."""

    response = llm.invoke(prompt)
    action = response.content.strip()

    print(f"propose_node: proposed action -> {action}")

    return {"proposed_action": action}

def human_gate_node(state: IncidentState) -> IncidentState:
    decision = interrupt({
        "hypothesis": state["hypothesis"],
        "proposed_action":state["proposed_action"],
        "question": "Approve this action? (yes/no)"
    })

    print(f"human_gate_node: received decision -> {decision}")
    return {"approved": decision}

def save_node(state: IncidentState) -> IncidentState:
    save_incident(
        service=state["service"],
        incident_description=state["incident"],
        hypothesis=state["hypothesis"],
        proposed_action=state["proposed_action"],
        approved=state["approved"]
    )
    return {}

def route_after_reason(state: IncidentState) -> str:
    if state["iterations"] < 2:
        return "act"
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
builder.add_node("propose", propose_node)
builder.add_node("human_gate", human_gate_node)
builder.add_node("save", save_node)

builder.add_edge(START, "plan")
builder.add_edge("plan", "act")
builder.add_edge("act", "reason")
builder.add_edge("propose", "human_gate")
builder.add_edge("human_gate", "save")
builder.add_edge("save", END)

builder.add_conditional_edges(
    "reason",
    route_after_reason,
    {"act": "act", "done": "propose"}
)

checkpointer = InMemorySaver()
graph = builder.compile(checkpointer=checkpointer)
config = {"configurable": {"thread_id": "incident-001"}}

if __name__ == "__main__":

    tools.set_incident("inc001")
    
    result = graph.invoke({
        "incident": "Checkout service error rate jumped from 0.1% to 12% at 14:32 UTC.",
        "service": "checkout",
        "plan": "",
        "evidence": [],
        "hypothesis": "",
        "hypothesis_history": [],
        "enough_evidence": "",
        "iterations": 0,
        "proposed_action": "",
        "approved": ""
    }, config=config)

    if "__interrupt__" in result:
        pause_info = result["__interrupt__"][0].value
        print("\n--- Agent is paused, waiting for approval ---")
        print("Hypothesis:", pause_info["hypothesis"])
        print("Proposed action:", pause_info["proposed_action"])

        human_answer = input(f"\n {pause_info['question']}")

        final_result = graph.invoke(Command(resume=human_answer), config=config)
        print("\n--- Final Result ---")
        print("Approved:", final_result["approved"])
        print("Proposed action:", final_result["proposed_action"])
    else:
        print("\nGraph finished without pausing:")
        print(result)