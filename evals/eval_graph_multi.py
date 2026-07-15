import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from multi_agent import (
    IncidentState, supervisor_plan, investigator, supervisor_judge,
    propose_node, route_after_judge, llm
)
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver

def auto_approve_node(state):
    print("auto_approve_node: approving automatically (eval mode)")
    return {"approved": "yes"}

builder = StateGraph(IncidentState)
builder.add_node("supervisor_plan", supervisor_plan)
builder.add_node("investigator", investigator)
builder.add_node("supervisor_judge", supervisor_judge)
builder.add_node("propose", propose_node)
builder.add_node("approve", auto_approve_node)

builder.add_edge(START, "supervisor_plan")
builder.add_edge("supervisor_plan", "investigator")
builder.add_edge("investigator", "supervisor_judge")
builder.add_conditional_edges(
    "supervisor_judge",
    route_after_judge,
    {"investigate": "supervisor_plan", "done": "propose"}
)
builder.add_edge("propose", "approve")
builder.add_edge("approve", END)

eval_checkpointer = InMemorySaver()
eval_graph_multi = builder.compile(checkpointer=eval_checkpointer)