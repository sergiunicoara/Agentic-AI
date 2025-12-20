🤖 Agentic AI: Multi-Source RAG with Human-in-the-Loop
A sophisticated AI agent system built to bridge the gap between private internal knowledge and real-time web data. This project features a Human-in-the-Loop (HITL) safety mechanism, ensuring that autonomous tool usage (like web searches) is only executed after explicit user approval.
🌟 Key Features
•	Hybrid Knowledge Retrieval: Leverages LlamaIndex to query private local documents and Tavily Search for live web intelligence.
•	Stateful Orchestration: Uses LangGraph to manage the agent's reasoning cycles and conversation state.
•	Safety Gate (HITL): Implements interrupt_before=["tools"] to pause the agent and request human permission before accessing external tools.
•	Interactive UI: A custom Streamlit dashboard that supports real-time chat, tool-call alerts, and action approval.
•	Production Ready: Containerized with Docker and served via a FastAPI backend with persistent memory checkpointers.
________________________________________
🛠️ Technical Stack
Component	Technology	Role
Orchestration	LangGraph	Manages the state machine and HITL interrupts.
Retrieval (RAG)	LlamaIndex	Handles document indexing and internal semantic search.
LLM Engine	OpenAI GPT-4o-mini	Powers the reasoning and decision-making logic.
External Search	Tavily API	Provides high-accuracy, real-time web search results.
API Backend	FastAPI	Exposes /ask and /act endpoints for frontend communication.
User Interface	Streamlit	Provides the interactive chat experience.
________________________________________
🏗️ System Architecture
1.	Thinking Phase: The LLM analyzes the user query. If it identifies a need for external or internal data, it suggests a "tool call".
2.	Interrupt: LangGraph catches the tool request and pauses execution.
3.	Human Approval: The Streamlit UI alerts the user. The user can Approve (continuing the search) or Reject (forcing the agent to answer with existing knowledge).
4.	Synthesis: The agent combines the tool output (if approved) into a final, natural language response.
________________________________________
📁 Project Structure
•	main.py: The FastAPI server containing the core LangGraph definition and memory management.
•	integrated_agent.py: The logic for the LlamaIndex RAG engine and tool definitions.
•	frontend.py: The Streamlit interface for the chat and approval workflow.
•	langgraph.json: Configuration for LangGraph CLI and Cloud deployments.
•	Dockerfile: Multi-stage build for deploying the API service.
________________________________________
🚀 Getting Started
1. Prerequisites
•	Python 3.10+
•	OpenAI API Key
•	Tavily API Key (for web search)
2. Installation
Bash
# Clone the repository
git clone https://github.com/your-username/Agentic-AI.git
cd Agentic-AI/rag-app

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
3. Environment Setup
Create a .env file in the rag-app directory:
Code snippet
OPENAI_API_KEY=your_openai_key
TAVILY_API_KEY=your_tavily_key
4. Running the Application
Bash
# Start the FastAPI backend
python main.py

# In a new terminal, start the Streamlit UI
streamlit run frontend.py
________________________________________
🔒 Security & Best Practices
•	Protected Keys: API keys are managed via .env and are strictly ignored by Git.
•	Isolated Environments: The venv/ folder is excluded to keep the repository lightweight and professional.
•	Internal Data Safety: Local vector storage and data directories are ignored to prevent leaking private documents.

