import os
from dotenv import load_dotenv
from typing import Annotated, Literal, TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

# 1. Setup
load_dotenv(override=True)
if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("Missing API Key")

# 2. Define the Tools ( The "Hands" of the Agent )

@tool
def search_internal_database(query: str):
    """
    Use this tool ONLY for questions about 'Project Omega', 'Salaries', or 'Employees'.
    It simulates querying a private SQL database.
    """
    # In a real app, you would connect to PostgreSQL/Chroma here.
    return f"DATABASE RESULT: Found secure data regarding '{query}'. Status: CONFIDENTIAL."

@tool
def search_web_wikipedia(query: str):
    """
    Use this tool for general knowledge questions like 'Who is the president?', 
    'Weather in Paris', or historical facts.
    """
    return f"WEB RESULT: According to Wikipedia, '{query}' is a popular topic."

# 3. Define the State ( The "Memory" )
# We just need to keep a list of messages (User -> AI -> Tool -> AI)
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]

# 4. Define the Brain ( The LLM )
# We "bind" the tools to the model so it knows they exist.
tools = [search_internal_database, search_web_wikipedia]
llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)
llm_with_tools = llm.bind_tools(tools)

# 5. Define the Nodes ( The Steps )

def chatbot_node(state: AgentState):
    """The thinking step: LLM decides what to do."""
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}

# 6. Define the Router ( The Decision Logic )
def router_logic(state: AgentState) -> Literal["tools", "__end__"]:
    """
    Checks the last message. 
    If the LLM wants to call a tool -> Go to 'tools' node.
    If the LLM just replied with text -> End.
    """
    messages = state["messages"]
    last_message = messages[-1]
    
    if last_message.tool_calls:
        return "tools"
    return "__end__"

# 7. Build the Graph ( The Assembly )
workflow = StateGraph(AgentState)

# Add the two main nodes
workflow.add_node("chatbot", chatbot_node)
workflow.add_node("tools", ToolNode(tools)) # ToolNode is a pre-built LangGraph component

# Define the flow
workflow.add_edge(START, "chatbot")

# Add the "Conditional Edge" (The fork in the road)
workflow.add_conditional_edges(
    "chatbot",
    router_logic
)

# If a tool was used, go back to the chatbot to generate the final answer
workflow.add_edge("tools", "chatbot")

# Compile the graph
app = workflow.compile()

# --- 8. TEST IT ---
print("\n--- TEST 1: Internal Question ---")
input_1 = {"messages": [("user", "What is the status of Project Omega?")]}
for event in app.stream(input_1):
    for key, value in event.items():
        print(f"Node '{key}': processed.")

print("\n--- TEST 2: External Question ---")
input_2 = {"messages": [("user", "Who won the World Cup in 2022?")]}
for event in app.stream(input_2):
    for key, value in event.items():
        print(f"Node '{key}': processed.")