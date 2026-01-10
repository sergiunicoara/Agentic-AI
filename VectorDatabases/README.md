# 🏆 The Global Vector Arena 2026
**A Multi-Engine Benchmarking Dashboard for Vector Databases**

This project provides a real-time "Battle Arena" to compare the performance, latency, and accuracy of the world's leading vector databases. It simulates a production environment where semantic search queries are tested against multiple backends simultaneously.

---

## 🚀 Supported Engines
The arena benchmarks five distinct vector database technologies:
* **Weaviate** (Cloud/Local Graph-based)
* **Milvus** (High-scale Distributed)
* **Pinecone** (Serverless Managed)
* **ChromaDB** (Developer-first Persistent)
* **FAISS** (The Gold Standard for Brute-force/Flat Indexing)

## 🧠 Technical Architecture
The system uses a unified **Embedding Model** (`all-MiniLM-L6-v2`) to transform text into 384-dimensional vectors. 

### Key Features:
* **Ground Truth Calculation**: Uses a FAISS Flat Index to establish a mathematical "Gold Standard" for every query.
* **Recall@1 Tracking**: Measures how often each engine successfully retrieves the "perfect" match compared to the brute-force truth.
* **Metadata Filtering**: Implements category-based filtering (Science, Engineering, Finance) to test engine precision.
* **Latency Benchmarking**: Visualizes query execution time (ms) across local and cloud-based instances.

---

## 🛠️ Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/sergiu123456789/Agentic-AI.git](https://github.com/sergiu123456789/Agentic-AI.git)
   cd Agentic-AI/VectorDatabases```


###Install dependencies:

```bash
pip install -r requirements.txt```

###Spin up Local Engines (Docker):

```bash
docker-compose up -d```

### Run the Arena:

```bash
python main.py```

###📊 Performance Metrics

The dashboard provides a dual-axis visualization:
Blue Bars (Latency): Lower is better. Shows the speed of retrieval.
Red Line (Recall): Higher is better. Shows the semantic accuracy of the approximate search.

###📁 Project Structure

vector_search.py: Core logic for engine connections and search.
main.py: Gradio-based UI for the Battle Arena.
docker-compose.yml: Configuration for Milvus, Weaviate, and ChromaDB containers.
rag-app/: A specialized sub-application demonstrating an integrated Agentic RAG workflow.

---

### 💡 How to add this to your project:
1.  **Open Notepad** (or your code editor).
2.  **Paste** the content above.
3.  **Save as** `README.md` inside your `C:\Users\Sergiu\Desktop\Projects\Agentic-AI\VectorDatabases` folder.
4.  **Push to GitHub:**
    ```cmd
    git add README.md
    git commit -m "Add professional README for Vector Arena"
    git push origin main
    ```
