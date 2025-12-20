# 🤖 Agentic AI: Multi-Source RAG with Human-in-the-Loop

A professional-grade AI Agent system designed to bridge the gap between
private internal knowledge and real-time web data. This project
implements a **Human-in-the-Loop (HITL)** safety mechanism, ensuring
that autonomous actions---such as web searches---are only executed after
explicit user approval.

------------------------------------------------------------------------

## 🌟 Key Features

-   **Hybrid Knowledge Retrieval**: Integrates LlamaIndex for semantic
    search over private documents and Tavily Search for live web
    intelligence.
-   **Stateful Orchestration**: Built with LangGraph to manage complex
    reasoning cycles, state transitions, and persistent conversation
    memory.
-   **Human-in-the-Loop (HITL)**: Uses `interrupt_before` logic to pause
    the agent and request human permission before accessing external
    tools.
-   **Interactive Dashboard**: Custom Streamlit interface handling
    real-time chat, tool-call alerts, and manual action approval
    (Approve / Reject).
-   **Cloud Ready**: Includes `langgraph.json` configuration for
    seamless deployment to LangGraph Cloud or local servers.

------------------------------------------------------------------------

## 🛠️ Technical Stack

  --------------------------------------------------------------------------
  Component               Technology                      Role
  ----------------------- ------------------------------- ------------------
  Orchestration           LangGraph                       State management
                                                          and HITL interrupt
                                                          logic

  Retrieval (RAG)         LlamaIndex                      Document
                                                          ingestion,
                                                          indexing, and
                                                          query engine

  LLM Engine              GPT-4o-mini                     Reasoning core for
                                                          intent
                                                          classification and
                                                          synthesis

  External Search         Tavily API                      High-fidelity web
                                                          search optimized
                                                          for LLM agents

  Backend API             FastAPI                         High-performance
                                                          REST API

  Frontend                Streamlit                       Client-side
                                                          interface and HITL
                                                          approvals
  --------------------------------------------------------------------------

------------------------------------------------------------------------

## 🏗️ System Workflow

The agent operates on a cyclic graph with a conditional **safety gate**:

1.  **Thinking Phase** -- The LLM determines whether the request
    requires internal RAG or an external web search.
2.  **Interrupt** -- If a tool is required, LangGraph pauses execution.
3.  **User Approval** -- Streamlit UI prompts the user to Approve or
    Reject the tool call.
4.  **Final Response** -- The agent synthesizes all gathered data into a
    concise answer.

------------------------------------------------------------------------

## 📁 Project Structure

-   **main.py** -- FastAPI server compiling the LangGraph workflow with
    a `MemorySaver` checkpointer.
-   **integrated_agent.py** -- LlamaIndex `VectorStoreIndex` and custom
    tool definitions.
-   **frontend.py** -- Streamlit application managing session state and
    HITL UI.
-   **langgraph.json** -- Deployment manifest for the LangGraph
    ecosystem.
-   **requirements.txt** -- Dependency list including FastAPI,
    LangChain, and LlamaIndex.

------------------------------------------------------------------------

## 🚀 Installation & Setup

### 1. Prerequisites

-   Python 3.10+
-   OpenAI API Key
-   Tavily API Key

### 2. Environment Configuration

Create a `.env` file in the project root:

``` env
OPENAI_API_KEY=your_key_here
TAVILY_API_KEY=your_key_here
```

### 3. Local Execution

``` bash
pip install -r requirements.txt
python main.py
streamlit run frontend.py
```

### 4. Docker Deployment

``` bash
docker build -t rag-app .
docker run -p 8000:8000 rag-app
```

------------------------------------------------------------------------

## 🔒 Security & Best Practices

-   **Ignored Files**: `.gitignore` excludes `.env`, `venv/`, and local
    vector storage (`storage/`).
-   **HITL Safety**: No external web search executes without explicit
    human authorization, preventing unintended API usage.

------------------------------------------------------------------------
