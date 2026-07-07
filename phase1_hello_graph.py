from typing import TypedDict
from langgraph.graph import StateGraph, START, END

class GraphState(TypedDict):
    message:str

def node_a(state: GraphState) -> GraphState:
    print("Running node_a. Current State:", state)
    return {"message" : "hello from node_a"}

def node_b(state: GraphState) -> GraphState:
    print("Running node_b. Current state:", state)
    return {"message" : state["message"] + " ->seen by node_b"}

builder = StateGraph(GraphState)

builder.add_node("node_a", node_a)
builder.add_node("node_b", node_b)

builder.add_edge(START, "node_a")
builder.add_edge("node_a", "node_b")
builder.add_edge("node_b", END)

graph = builder.compile()
    
if __name__ == "__main__":
    result = graph.invoke({"message": "start"})
    print("\n Final state:", result)