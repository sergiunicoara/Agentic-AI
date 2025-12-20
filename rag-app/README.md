🤖 Agentic AI: Multi-Source RAG with Human-in-the-LoopA sophisticated AI agent system built to bridge the gap between private internal knowledge and real-time web data. This project features a Human-in-the-Loop (HITL) safety mechanism, ensuring that autonomous tool usage (like web searches) is only executed after explicit user approval.🌟 Key FeaturesHybrid Knowledge Retrieval: Leverages LlamaIndex to query private local documents and Tavily Search for live web intelligence.Stateful Orchestration: Uses LangGraph to manage the agent's reasoning cycles and conversation state.Safety Gate (HITL): Implements interrupt_before=["tools"] to pause the agent and request human permission before accessing external tools.Interactive UI: A custom Streamlit dashboard that supports real-time chat, tool-call alerts, and action approval.Production Ready: Containerized with Docker and served via a FastAPI backend with persistent memory checkpointers.🛠️ Technical StackComponentTechnologyRoleOrchestrationLangGraphManages the state machine and HITL interrupts.Retrieval (RAG)LlamaIndexHandles document indexing and internal semantic search.LLM EngineOpenAI GPT-4o-miniPowers the reasoning and decision-making logic.External SearchTavily APIProvides high-accuracy, real-time web search results.API BackendFastAPIExposes /ask and /act endpoints for frontend communication.User InterfaceStreamlitProvides the interactive chat experience.🏗️ System ArchitectureThinking Phase: The LLM analyzes the user query. If it identifies a need for external or internal data, it suggests a "tool call".Interrupt: LangGraph catches the tool request and pauses execution.Human Approval: The Streamlit UI alerts the user. The user can Approve (continuing the search) or Reject (forcing the agent to answer with existing knowledge).Synthesis: The agent combines the tool output (if approved) into a final, natural language response.📁 Project Structuremain.py: The FastAPI server containing the core LangGraph definition and memory management.integrated_agent.py: The logic for the LlamaIndex RAG engine and tool definitions.frontend.py: The Streamlit interface for the chat and approval workflow.langgraph.json: Configuration for LangGraph CLI and Cloud deployments.Dockerfile: Multi-stage build for deploying the API service.🚀 Getting Started1. PrerequisitesPython 3.10+OpenAI API KeyTavily API Key (for web search)2. InstallationBash# Clone the repository
git clone https://github.com/your-username/Agentic-AI.git
cd Agentic-AI/rag-app

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
3. Environment SetupCreate a .env file in the rag-app directory:Code snippetOPENAI_API_KEY=your_openai_key
TAVILY_API_KEY=your_tavily_key
4. Running the ApplicationBash# Start the FastAPI backend
python main.py

# In a new terminal, start the Streamlit UI
streamlit run frontend.py
🔒 Security & Best PracticesProtected Keys: API keys are managed via .env and are strictly ignored by Git.Isolated Environments: The venv/ folder is excluded to keep the repository lightweight and professional.Internal Data Safety: Local vector storage and data directories are ignored to prevent leaking private documents.
