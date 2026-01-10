# Global Vector Arena 2026

A benchmarking and visualization application for comparing vector database engines on semantic search latency and recall. The project embeds text using Sentence Transformers, runs similarity search across multiple vector backends, and presents results via an interactive Gradio UI.

## Overview

The application evaluates several popular vector search engines against a shared dataset and query, measuring:

* **Latency (ms)** for top-1 similarity search
* **Recall@1 (%)** against an exact FAISS ground truth

Results are displayed both as a markdown table and a dual-axis chart.

## Supported Engines

* FAISS (ground truth and benchmark)
* ChromaDB
* Pinecone
* Weaviate
* Milvus

> Note: Some engines use simplified or simulated logic in the demo UI. Full production integrations can be added where indicated in the code.

## Architecture

* **Embedding model:** `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions)
* **Benchmark driver:** `vector_search.py`
* **UI:** Gradio Blocks
* **Visualization:** Matplotlib (latency bars + recall line)

## Prerequisites

* Python 3.9+
* Docker and Docker Compose (optional, recommended)

## Installation

### Option 1: Local Python

```bash
pip install -r requirements.txt
python vector_search.py
```

The application will launch a local Gradio server.

### Option 2: Docker Compose

```bash
docker compose up --build
```

This will build and start the application using the provided `docker-compose.yml`.

## Usage

1. Enter a **Battle Query** (natural language search string).
2. Select a **Metadata Filter** (All, Engineering, Finance, Science).
3. Click **Start Battle**.
4. Review:

   * Returned document per engine
   * Latency in milliseconds
   * Recall@1 compared to the FAISS ground truth

## Data

The demo uses a small in-memory dataset with semantic categories:

* Science
* Engineering
* Finance

Embeddings are generated at startup and reused across engines.

## Configuration

Key configuration values are defined at the top of `vector_search.py`:

* Embedding model
* Vector dimension
* API keys and client configuration

### Security Notice

The Pinecone API key is currently hard-coded for demonstration purposes.

**Do not do this in production.**

Recommended alternatives:

* Environment variables
* `.env` file with Docker Compose
* Secret managers (AWS, GCP, Vault, etc.)

## Output

* Markdown results table per query
* Dual-axis chart:

  * Bars: latency (ms)
  * Line: Recall@1 (%)

## Limitations

* Small dataset intended for demonstration, not load testing
* Some backend calls are simplified or mocked
* Not suitable for performance claims without further instrumentation


