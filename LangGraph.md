# Agentic Workflows with LangGraph + Tavily + Amadeus + Custom Tools + Gradio

> Build a stateful, multi-agent workflow that plans travel, searches the web, calls Amadeus for live offers, and lets users steer the loop via a Gradio UI. 
---

## ✨ What you’ll build

- **A LangGraph workflow** with:
  - Shared **State** (user goal, working plan, tool results, chat history)
  - Modular **Agents** (Planner, WebSearch, Travel, and a Custom tool agent)
  - **Conditional edges** that route based on state (success/fail/need-clarification)
- **Tools**
  - **Tavily** for web search & extraction
  - **Amadeus** for travel offers
  - A **custom Python tool** (e.g., budget checker or policy validator)
- **Human-in-the-loop UI** with **Gradio** for interactive control

---

## 🧱 Architecture

```
User ↔ Gradio UI
         │
         ▼
   LangGraph Orchestrator (StateGraph)
   ├── PlannerAgent (LLM)
   ├── WebSearchAgent (Tavily)
   ├── TravelAgent (Amadeus)
   ├── CustomToolAgent (your business logic)
   └── Router (conditional edges based on State)
```

- **State** (typed dict): `messages`, `goal`, `plan`, `cursor`, `results`, `errors`, `next_action`, `complete`.
- **Agents**: pure functions that read/write State.
- **Router**: inspects `next_action` / flags to choose the next node.

---

## 🧰 Prerequisites

- Python 3.10+
- API keys: **Tavily** (`TAVILY_API_KEY`), **Amadeus** (`AMADEUS_CLIENT_ID`, `AMADEUS_CLIENT_SECRET`)
- Libraries: `langgraph`, `langchain-core`, `tavily-python`, `amadeus`, `gradio`, your LLM client.

---

## 🚀 Installation

```bash
pip install -q --upgrade langchain langgraph langchain_openai tavily-python amadeus python-dotenv gradio langchain_community graphviz

```

Create `.env`:

```bash
TAVILY_API_KEY=...
AMADEUS_CLIENT_ID=...
AMADEUS_CLIENT_SECRET=...
```

---

## 🗺️ Define the State

```python
# state.py
from typing import TypedDict, Annotated, Sequence, List, Tuple, Optional, Any, Union, Literal,  Tuple
from langchain_core.messages import BaseMessage, ToolMessage, HumanMessage, AIMessage, SystemMessage

class AgentState(TypedDict):
    input_text: str
    summary: str

tools = [
    tavily_search_tool,
    search_flights_tool,
    get_current_date_tool,
]
```

---

## 🧠 Agents (nodes)

> Each node is a function: `def node(state: GraphState) -> GraphState`.

### PlannerAgent

```python
def search_flights_tool(
    origin_code: str,
    destination_code: str,
    departure_date: str,
    return_date: str | None = None,
    adults: int = 1,
    travel_class: str = "ECONOMY",
    currency: str = "USD",
    max_offers: int = 5,
):
    """
    Searches live flight prices and availability via Amadeus Flight Offers Search API.
    Required:
        origin_code, destination_code – IATA airport/city codes (e.g., 'YYZ', 'LHR')
        departure_date – 'YYYY-MM-DD'
    Optional:
        return_date – for round‑trips; omit for one‑way
        adults – number of adult passengers (default 1)
        travel_class – 'ECONOMY', 'PREMIUM_ECONOMY', 'BUSINESS', 'FIRST'
        currency – 3‑letter code for pricing (default USD)
        max_offers – how many offers to list back
    """

    print(
        f"DEBUG: Calling Amadeus Flight Search – "
        f"{origin_code}->{destination_code}, "
        f"Depart {departure_date}, Return {return_date}, "
        f"Adults {adults}, Class {travel_class}"
    )
```

### WebSearchAgent (Tavily)

```python
flight_search_params = {
        "originLocationCode": origin_code,
        "destinationLocationCode": destination_code,
        "departureDate": departure_date,
        "adults": adults,
        "travelClass": travel_class,
        "currencyCode": currency,
        "max": max_offers,
    }
    if return_date:
        flight_search_params["returnDate"] = return_date

    response = amadeus_client.shopping.flight_offers_search.get(**flight_search_params)

```

### TravelAgent (Amadeus)

```python
import os
from amadeus import Client, ResponseError

amadeus = Client(
    client_id=os.getenv("AMADEUS_CLIENT_ID"),
    client_secret=os.getenv("AMADEUS_CLIENT_SECRET")
)

def travel_node(state: GraphState) -> GraphState:
    try:
        origin, dest, depart = "MAD","CDG","2025-09-15"
        offers = amadeus.shopping.flight_offers_search.get(
            originLocationCode=origin,
            destinationLocationCode=dest,
            departureDate=depart,
            adults=1
        ).data
        state.setdefault("results", []).append(
            {"tool":"amadeus.flight_offers_search","payload":offers}
        )
        state["next_action"] = "custom"
    except ResponseError as e:
        state.setdefault("errors", []).append(str(e))
        state["next_action"] = "ask_user"
    return state
```

### CustomToolAgent

```python
def get_current_date_tool():
    """Returns the current date in 'YYYY-MM-DD' format. Useful for finding flights/hotels relative to today."""
    return date.today().isoformat()

app_current_date = build_graph_one_tool([get_current_date_tool])

```

### AskUser

```python
prompt = "I want the latest news about New York, I'm planning to visit from 2025-06-01 to 2025-06-04, leaving from Toronto. Please fetch security and travel advisories, find the cheapest flight for one adult. Finally, format the combined output."
output, history = app_call(app_travel_agent, prompt)
```

---

## 🔀 Wiring the Workflow with LangGraph

```python
#LangGraph imports (Updated based on recent versions)
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode  # Preferred way to handle tool execution

workflow = StateGraph(AgentState)

# Let's add a node, which is the summarize function we defined before
workflow.add_node("summarize", summarize_step)

# Let's define Edges, which define how data flows between nodes
workflow.add_edge("summarize", "translate")

workflow.add_node("translate", translate_step)

workflow.set_entry_point("summarize")
workflow.compile()
```

---

## 🧪 Running the Graph

```python
initial_state = {
        "input_text": sample_text,
        "summary": "",
        "translated_summary": ""}
    
# Run the graph
result = graph.invoke(initial_state)
```

---

## 🖥️ Gradio UI

```python
travel_chatbot_interface = gr.ChatInterface(
    fn = travel_agent_chat,
    chatbot = gr.Chatbot(
        height = 650,
        label = "AI Travel Agent",
        show_copy_button = True,
        bubble_full_width = False,
        render_markdown = True,
    ),
    
    textbox = gr.Textbox(
        placeholder = "Plan your trip! Ask about attractions, flights, hotels...", container = False, scale = 7
    ),
    title = "✈️ LangGraph AI Travel Agent 🌍",
    description = "Your stateful travel assistant…",
    examples = [
        ["What are the top 3 tourist attractions in Tokyo (HND)?"],
        ["Find flights from London (LHR) to Paris (CDG) leaving next month for 4-day trip"],
        ["Book a hotel for 5 nights in NYC next month"],
    ],
    cache_examples = False,
)
```

---

## ✅ End-to-end run

```python
travel_chatbot_interface.launch()
```

---

## 🧩 Extending the workflow

- Add parallel branches with LangGraph reducers.
- Integrate hotel offers, attractions, or calendar sync.
- Insert guardrails before tool calls.

---
