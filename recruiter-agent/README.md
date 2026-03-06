# 🚀 Sergiu – AI Recruiter Tour Agent
### Production-ready AI Agent (Google/Kaggle Agents Style)

This project implements a production-grade AI Recruiter Tour Agent inspired by the Google/Kaggle “Agents” course. It acts as an interactive recruiter companion, helping hiring managers instantly understand your strongest qualifications through agentic workflows.

---

## 🧠 Core Capabilities

* **✔️ Recruiter-Aware Entry:** Tailors first messages based on referral source (GitHub/LinkedIn).
* **✔️ Role & Criteria Extraction:** Understands nuances of Senior ML, AI, and Data Science roles.
* **✔️ Project Relevance Ranking:** Uses embeddings to compute a shortlist of relevant projects.
* **✔️ Deep-Dive Flow:** Explains impact and role-match project-by-project.
* **✔️ ATS-Ready Outputs:** Generates polished summaries and recruiter email drafts.
* **✔️ CV RAG (Gemini Embeddings):** High-precision retrieval using `text-embedding-004`.
* **✔️ Observability:** Lightweight trajectory logging with LLM-judge evaluations (1–5 score).
* **✔️ Voice Interface:** Browser-native speech-to-text (mic input) and text-to-speech (AI responses read aloud) via the Web Speech API — no extra API keys required.

---

## 🏗️ Tech Stack

* **Backend:** FastAPI, Uvicorn
* **LLM:** Gemini 1.5 Flash (`google-genai`)
* **Embeddings:** `models/text-embedding-004`
* **Frontend:** Lightweight JS chat UI with voice (Web Speech API)
* **Cloud:** Google Cloud Run (Containerized)

---

## 📁 Project Structure

```text
recruiter-agent/
├── README.md           <-- You are here
├── deploy.ps1          <-- Automated Zero-Cost Deployment
├── Dockerfile          <-- Optimized Python-slim container
├── requirements.txt    <-- Dependencies
├── main.py             <-- Entry point
├── app/
│   ├── agent.py        <-- Orchestrator & Logic
│   ├── cv_rag.py       <-- Vector Search / RAG
│   ├── server.py       <-- API Routes
│   └── quality.py      <-- Trajectory Logging
└── frontend/
    └── index.html      <-- Chat UI with voice (STT + TTS)
```
## 🎙️ Voice Interface

The chat UI includes browser-native voice support — no extra API keys or backend changes required.

| Feature | How to use |
|---|---|
| **Speech-to-text** | Click the mic icon next to the Send button → speak → transcript fills the input |
| **Text-to-speech** | Click the small speaker icon on any AI message bubble to replay it |
| **Auto-speak** | Toggle `🔇 Auto-speak` in the chat header → turns `🔊` → every new AI response is read aloud automatically |
| **Stop** | A red `■ Stop` button appears in the header while speech is playing; click to cancel immediately |

> Requires Chrome or Edge. Mic buttons are hidden automatically in browsers that don't support the Web Speech API (e.g. Firefox).

---

## 🚀 Deployment (Zero-Cost Optimized)
This project is configured to run on the Google Cloud Free Tier. The included deploy.ps1 script ensures the service "scales to zero" when not in use.

Prerequisites
Google Cloud SDK and Docker Desktop installed.

GOOGLE_API_KEY from Google AI Studio.

Deployment Steps
Open PowerShell in the project root.

Run the deployment script:

PowerShell

.\deploy.ps1
The script will automatically create the Artifact Registry repository, build the image, and deploy to Cloud Run with zero-cost settings.

## 💰 Cost-Control Features
--min-instances 0: Ensures you are not billed for idle time.

--cpu-throttling: Stops CPU billing immediately after request completion.

Artifact Registry: Uses standard Docker storage (Keep < 500MB for free tier).

