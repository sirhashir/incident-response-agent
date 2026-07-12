from typing import TypedDict
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, START, END

class IncidentState(TypedDict):
    incident: str
    plan: str

llm = ChatOllama(model = "llama3.1:8b", temperature = 0) #temperature controls randomness

def plan_node(state: IncidentState) -> IncidentState:
    prompt = f"""You are an on-call engineer investigating a production incident. 
    Incident: {state['incident']}
    In 2-3 sentences, describe what you would investigate first and why."""

    response = llm.invoke(prompt)
    print("LLM raw response object type:", type(response))
    print("LLM said: \n", response.content)
    
    return {"plan": response.content}

builder = StateGraph(IncidentState)
builder.add_node("plan", plan_node)
builder.add_edge(START, "plan")
builder.add_edge("plan", END)
graph = builder.compile()

if __name__ == "__main__":
    result = graph.invoke({
        "incident": "Checkout service error rate jumped from 0.1% to 12% at 14:32 UTC. No recent deploys reported.",
        "plan": ""
    })
    print("\n Final state:")
    print(result)