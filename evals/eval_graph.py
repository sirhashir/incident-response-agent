import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))
from agent import (
    IncidentState, plan_node, act_node, reason_node,
    propose_node, route_after_reason, llm
)
from  langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver

def auto_approve_node(state):
    print("auto_approve_node: approving automatically (eval mode)")
    return {"approved": "yes"}

builder = StateGraph(IncidentState)
builder.add_node("plan", plan_node)
builder.add_node("act", act_node)
builder.add_node("reason", reason_node)
builder.add_node("propose", propose_node)
builder.add_node("approve", auto_approve_node)

builder.add_edge(START, "plan")
builder.add_edge("plan", "act")
builder.add_edge("act", "reason")
builder.add_conditional_edges("reason", route_after_reason, {"act": "act", "done": "propose"})
builder.add_edge("propose", "approve")
builder.add_edge("approve", END)

eval_checkpointer = InMemorySaver()
eval_graph = builder.compile(checkpointer=eval_checkpointer)