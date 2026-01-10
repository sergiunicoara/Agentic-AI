from dotenv import load_dotenv
load_dotenv(override=True)

import os
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Annotated, Optional
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI

try:
    from langchain_tavily import TavilySearchResults
except ImportError:
    from langchain_community.tools.tavily_search import TavilySearchResults

app_api = FastAPI()

class State(TypedDict):
    messages: Annotated[list, add_messages]

tool = TavilySearchResults(max_results=2)
tools = [tool]
llm = ChatOpenAI(model="gpt-4o-mini").bind_tools(tools)

def chatbot(state: State):
    return {"messages": [llm.invoke(state["messages"])]}

builder = StateGraph(State)
builder.add_node("chatbot", chatbot)
builder.add_node("tools", ToolNode(tools))

builder.add_edge(START, "chatbot")
builder.add_conditional_edges("chatbot", tools_condition)
builder.add_edge("tools", "chatbot")

memory = MemorySaver()
graph = builder.compile(interrupt_before=["tools"])

class ChatRequest(BaseModel):
    question: str
    thread_id: str

@app_api.post("/ask")
async def ask(req: ChatRequest):
    config = {"configurable": {"thread_id": req.thread_id}}
    try:
        async for _ in graph.astream({"messages": [("user", req.question)]}, config, stream_mode="values"):
            pass
        
        snapshot = graph.get_state(config)
        is_paused = snapshot.next and snapshot.next[0] == "tools"
        
        return {
            "answer": snapshot.values["messages"][-1].content or "Agent is ready to search...",
            "is_paused": is_paused,
            "pending_tool": snapshot.values["messages"][-1].tool_calls[0] if is_paused else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app_api.post("/act")
async def act(action: str, req: ChatRequest):
    config = {"configurable": {"thread_id": req.thread_id}}
    try:
        if action == "approve":
            # Resume exactly where left off
            async for _ in graph.astream(None, config, stream_mode="values"):
                pass
        elif action == "reject":
            # Provide rejection feedback to the LLM
            graph.update_state(config, {"messages": [("user", "Action rejected. Please answer directly based on what you know.")]}, as_node="chatbot")
            async for _ in graph.astream(None, config, stream_mode="values"):
                pass

        final_snapshot = graph.get_state(config)
        return {"answer": final_snapshot.values["messages"][-1].content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app_api, host="0.0.0.0", port=8000)