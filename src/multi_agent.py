from typing import TypedDict, Annotated
import operator
from tools import fetch_logs, get_deploy_history, query_metrics
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import interrupt, Command
from memory import save_incident, recall_similar
import tools

llm = ChatOllama(model="llama3.1:8b", temperature=0)

class IncidentState(TypedDict):
    incident: str
    service: str
    past_incidents: list
    investigation_goal: str
    findings: Annotated[list, operator.add]
    hypothesis: str
    hypothesis_history: Annotated[list, operator.add]
    enough_evidence: str
    iterations: int
    proposed_action: str
    approved: str

def supervisor_plan(state: IncidentState) -> IncidentState:
    past = recall_similar(state["service"])

    show_history = state["iterations"] > 0

    if show_history and past:
        history_text = "\n".join([
            f"- Past incident: {p['incident']} | Cause: {p['hypothesis']} | Action: {p['proposed_action']}"
            for p in past
        ])
        history_block = f"Past incidents for this service:\n{history_text}"
    else:
        history_block = "Do not consider past incident history yet, focus only on the current incident and findings below."
    
    already_investigated = [f["goal"] for f in state["findings"]]
    prompt = f"""You are a supervisor directing an investigation into this incident: {state['incident']}

            {history_block}

            Already investigated: {already_investigated if already_investigated else "nothing yet"}

            Set ONE specific investigation goal for what to check next, based on the actual details
            of THIS incident described above. Be concrete about what you are trying to find out.

            Answer in one sentence: what should be investigated next, and why."""

    response = llm.invoke(prompt)
    goal = response.content.strip()

    print(f"supervisor_plan: goal -> {goal}")
 
    return {
        "investigation_goal": goal,
        "past_incidents": past
    }

def investigator(state: IncidentState) -> IncidentState:
    goal = state["investigation_goal"]
    service = state["service"]
    already_used = [f["tool"] for f in state["findings"]]
    prompt = f"""You are an investigator. Your supervisor has given you this goal:
            {goal}

            Available tools:
            - fetch_logs: recent log lines for the service
            - get_deploy_history: recent deployments for the service
            - query_metrics: recent CPU, memory, and error rate metrics for the service

            Tools already used: {already_used if already_used else "none yet"}

            Which single tool best serves this goal? Answer with exactly one word:
            fetch_logs, get_deploy_history, or query_metrics"""
    
    response = llm.invoke(prompt)
    choice = response.content.strip().lower()

    all_tools = ["fetch_logs", "get_deploy_history", "query_metrics"]
    unused = [t for t in all_tools if t not in already_used]

    if "deploy" in choice:
        tool_used = "get_deploy_history"
    elif "metric" in choice:
        tool_used = "query_metrics"
    else:
        tool_used = "fetch_logs"
    
    if tool_used in already_used and unused:
        tool_used = unused[0]
        print(f"investigator: repeated tool, overriding to '{tool_used}'")
    
    if tool_used == "get_deploy_history":
        result = get_deploy_history(service)
    elif tool_used == "query_metrics":
        result = query_metrics(service)
    else:
        result = fetch_logs(service)

    print(f"investigator: goal='{goal[:60]}...' used='{tool_used}'")

    return {
        "findings": [{"goal": goal, "tool": tool_used, "result": result}]
    }

def supervisor_judge(state: IncidentState) -> IncidentState:

    findings_text = ""
    for f in state["findings"]:
        findings_text += f"\nGoal: {f['goal']}\nTool used: {f['tool']}\nResult: {f['result']}\n"
    past = state["past_incidents"]
    show_history = state["iterations"] > 0

    if show_history and past:
        history_text = "\n".join([
            f"- Past incident: {p['incident']} | Cause: {p['hypothesis']} | Action: {p['proposed_action']}"
            for p in past
        ])
        history_block = f"Past incidents for this service:\n{history_text}"
    else:
        history_block = "Do not consider past incident history yet. Base your hypothesis only on the findings above."

    prompt = f"""You are a supervisor reviewing an investigation into this incident: {state['incident']}

            Findings reported by your investigator:
            {findings_text}

            {history_block}

            Based on the findings{" AND the history" if show_history else ""}, answer two things:
            1. What is your best hypothesis for the root cause? Base this primarily on the findings.
            {"Only mention history if it genuinely matches, don't force a connection." if show_history else ""}
            (1-2 sentences)
            2. Is this hypothesis well-supported by the findings, such that a competent engineer
            could act on it? Answer "yes" if it's reasonably supported, even without 100%
            certainty. Answer "no" only if findings are genuinely insufficient or contradictory.

            Format your answer exactly like this:
            HYPOTHESIS: <your hypothesis>
            ENOUGH: <yes or no>"""
    
    response = llm.invoke(prompt)
    text = response.content
    print("supervisor_judge raw output:\n", text)

    hypothesis = ""
    enough = "no"
    for line in text.split("\n"):
        if line.startswith("HYPOTHESIS:"):
            hypothesis = line.replace("HYPOTHESIS:", "").strip()
        if line.startswith("ENOUGH:"):
            enough = line.replace("ENOUGH:", "").strip().lower()
    
    return {
        "hypothesis": hypothesis,
        "hypothesis_history": [hypothesis],
        "enough_evidence": enough,
        "iterations": state["iterations"] + 1
    }

def route_after_judge(state: IncidentState) -> str:
    if state["iterations"] < 2:
        return "investigate"
    if state["enough_evidence"] == "yes":
        return "done"
    if state["iterations"] >= 3:
        return "done"
    return "investigate"

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

Answer in one sentence, describing exactly what action to take."""

    response = llm.invoke(prompt)
    action = response.content.strip()
    print(f"propose_node: proposed action -> {action}")
    return {"proposed_action": action}


def human_gate_node(state: IncidentState) -> IncidentState:
    decision = interrupt({
        "hypothesis": state["hypothesis"],
        "proposed_action": state["proposed_action"],
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

builder = StateGraph(IncidentState)
builder.add_node("supervisor_plan", supervisor_plan)
builder.add_node("investigator", investigator)
builder.add_node("supervisor_judge", supervisor_judge)
builder.add_node("propose", propose_node)
builder.add_node("human_gate", human_gate_node)
builder.add_node("save", save_node)

builder.add_edge(START, "supervisor_plan")
builder.add_edge("supervisor_plan", "investigator")
builder.add_edge("investigator", "supervisor_judge")
builder.add_conditional_edges(
    "supervisor_judge",
    route_after_judge,
    {"investigate": "supervisor_plan", "done": "propose"}
)
builder.add_edge("propose", "human_gate")
builder.add_edge("human_gate", "save")
builder.add_edge("save", END)

checkpointer = InMemorySaver()
graph = builder.compile(checkpointer=checkpointer)

config = {"configurable": {"thread_id": "incident-001"}}

if __name__ == "__main__":
    tools.set_incident("inc001")

    result = graph.invoke({
        "incident": "Checkout service error rate jumped from 0.1% to 12% at 14:32 UTC.",
        "service": "checkout",
        "past_incidents": [],
        "investigation_goal": "",
        "findings": [],
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
        human_answer = input(f"\n{pause_info['question']} ")
        final_result = graph.invoke(Command(resume=human_answer), config=config)
        print("\n--- Final Result ---")
        print("Approved:", final_result["approved"])
        print("Proposed action:", final_result["proposed_action"])
    else:
        print("\nGraph finished without pausing:")
        print(result)