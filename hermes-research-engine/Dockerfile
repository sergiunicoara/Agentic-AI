FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data
ENV LANCEDB_PATH=/data/vector_store
ENV EPISODIC_PATH=/data/episodes.json

EXPOSE 8000

# Use shell form so $PORT env var is expanded by Railway
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
