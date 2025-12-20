🤖 Agentic AI: Multi-Source RAG with Human-in-the-Loop
A professional-grade AI Agent system designed to bridge the gap between private internal knowledge and real-time web data. This project implements a Human-in-the-Loop (HITL) safety mechanism, ensuring that autonomous actions—like web searches—are only executed after explicit user approval.
🌟 Key Features
•	Hybrid Knowledge Retrieval: Integrates LlamaIndex for semantic search over private documents and Tavily Search for live web intelligence.
•	Stateful Orchestration: Built with LangGraph to manage complex reasoning cycles, state transitions, and persistent conversation memory.
•	Human-in-the-Loop (HITL): Utilizes interrupt_before logic to pause the agent and request human permission before accessing external tools.
•	Interactive Dashboard: A custom Streamlit interface that handles real-time chat, tool-call alerts, and manual action approval (Approve/Reject).
•	Cloud Ready: Includes langgraph.json configuration for seamless deployment to LangGraph Cloud or local servers.
________________________________________
🛠️ Technical Stack
Component	Technology	Role
Orchestration	LangGraph	State management and HITL interrupt logic.
Retrieval (RAG)	LlamaIndex	Document ingestion, indexing, and query engine.
LLM Engine	GPT-4o-mini	The reasoning core for intent classification and synthesis.
External Search	Tavily API	High-fidelity web search specialized for LLM agents.
Backend API	FastAPI	High-performance REST API for agent communication.
Frontend	Streamlit	Client-side interface for user interaction.
________________________________________
🏗️ System Workflow
The agent operates on a cyclic graph with a conditional "safety gate":
1.	Thinking Phase: The LLM determines if the answer requires internal data (RAG) or a web search.
2.	Interrupt: If a tool is needed, LangGraph triggers an interrupt, pausing the process.
3.	User Approval: The Streamlit UI displays a warning. The user can Approve (executes search) or Reject (forces the agent to answer using only its current knowledge).
4.	Final Response: The agent synthesizes all gathered data into a concise final answer.
________________________________________
📁 Project Structure
•	main.py: FastAPI server that compiles the LangGraph workflow with a MemorySaver checkpointer.
•	integrated_agent.py: Implementation of the LlamaIndex VectorStoreIndex and the custom tool definitions.
•	frontend.py: Streamlit application handling session state and the HITL approval UI.
•	langgraph.json: Deployment manifest for the LangGraph ecosystem.
•	requirements.txt: Comprehensive list of dependencies including fastapi, langchain, and llama-index.
________________________________________
🚀 Installation & Setup
1. Prerequisites
•	Python 3.10+
•	OpenAI API Key
•	Tavily API Key
2. Environment Configuration
Create a .env file in the root directory:
Code snippet
OPENAI_API_KEY=your_key_here
TAVILY_API_KEY=your_key_here
3. Local Execution
Bash
# Install dependencies
pip install -r requirements.txt

# Start the FastAPI backend
python main.py

# In a separate terminal, start the UI
streamlit run frontend.py
4. Docker Deployment
Bash
docker build -t rag-app .
docker run -p 8000:8000 rag-app
________________________________________
🔒 Security & Best Practices
•	Ignored Files: The .gitignore prevents sensitive data (.env), virtual environments (venv/), and local vector storage (storage/) from being pushed to GitHub.
•	HITL Safety: No external web search is performed without explicit human authorization, preventing unintended API usage.

