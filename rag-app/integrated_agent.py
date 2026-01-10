import os
from typing import Annotated, Literal, TypedDict
from dotenv import load_dotenv

# LangChain / LangGraph Imports
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

# LlamaIndex Imports
from llama_index.core import (
    VectorStoreIndex, 
    SimpleDirectoryReader, 
    StorageContext, 
    load_index_from_storage
)
from tavily import TavilyClient

# --- 1. SETUP & CONFIGURATION ---
load_dotenv(override=True)

if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("Missing OPENAI_API_KEY!")

PERSIST_DIR = "./storage"

# --- 2. INITIALIZE LLAMAINDEX RAG (Global Scope) ---
print("--- Initializing Internal Knowledge Base ---")
if os.path.exists(PERSIST_DIR):
    storage_context = StorageContext.from_defaults(persist_dir=PERSIST_DIR)
    index = load_index_from_storage(storage_context)
else:
    if not os.path.exists("./data"):
        os.makedirs("./data")
    documents = SimpleDirectoryReader("./data").load_data()
    index = VectorStoreIndex.from_documents(documents)
    index.storage_context.persist(persist_dir=PERSIST_DIR)

rag_engine = index.as_query_engine(similarity_top_k=3)

# --- 3. DEFINE REAL TOOLS ---

@tool
def search_internal_database(query: str):
    """
    Useful for questions about internal projects (Omega), salaries, employees, or policies.
    """
    try:
        response = rag_engine.query(query)
        return str(response)
    except Exception as e:
        return f"Error: {e}"

@tool
def search_web_tavily(query: str):
    """
    Useful for general knowledge, current events, or public info.
    """
    try:
        if not os.getenv("TAVILY_API_KEY"):
            return "Error: Tavily API Key missing."
        tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
        response = tavily.search(query=query)
        return str([result['content'] for result in response['results'][:3]])
    except Exception as e:
        return f"Error searching web: {e}"

# --- 4. DEFINE GRAPH COMPONENTS ---

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]

tools = [search_internal_database, search_web_tavily]
llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)
llm_with_tools = llm.bind_tools(tools)

# --- KEY FIX: SYSTEM PROMPT ---
sys_msg = SystemMessage(content="""
You are a helpful assistant. 
1. Use the 'search_internal_database' tool for questions about the company or projects.
2. Use 'search_web_tavily' for general world knowledge.
3. CRITICAL: Once you receive a tool output that answers the question, STOP using tools and write your final answer to the user.
""")

def chatbot_node(state: AgentState):
    # We prepend the system message to the history so the model knows its instructions
    messages = [sys_msg] + state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

def router_logic(state: AgentState) -> Literal["tools", "__end__"]:
    messages = state["messages"]
    last_message = messages[-1]
    
    if last_message.tool_calls:
        return "tools"
    return "__end__"

# --- 5. BUILD THE GRAPH ---
workflow = StateGraph(AgentState)

workflow.add_node("chatbot", chatbot_node)
workflow.add_node("tools", ToolNode(tools))

workflow.add_edge(START, "chatbot")
workflow.add_conditional_edges("chatbot", router_logic)
workflow.add_edge("tools", "chatbot")

graph_app = workflow.compile()