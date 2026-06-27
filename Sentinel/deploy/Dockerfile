FROM python:3.11-slim

# Build context is the Sentinel repo root (see deploy/deploy.sh):
#   docker build -f deploy/Dockerfile .
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# .dockerignore keeps .env, .git, caches and tests out of this layer.
COPY . .

ENV GOOGLE_GENAI_USE_VERTEXAI=TRUE
ENV GOOGLE_CLOUD_LOCATION=global

EXPOSE 8080
CMD ["python", "-m", "sentinel.a2a.server"]