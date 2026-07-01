# Stage 1: build the React dashboard
FROM node:20-slim AS dashboard-builder
WORKDIR /dashboard
COPY sentinel/dashboard/package*.json ./
RUN npm ci
COPY sentinel/dashboard/ .
RUN npm run build

# Stage 2: Python runtime
FROM python:3.11-slim

# Build context is the Sentinel repo root (see deploy/deploy.sh):
#   docker build -f deploy/Dockerfile .
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# .dockerignore keeps .env, .git, caches and tests out of this layer.
COPY . .

# Drop the React build output into a location the server can serve.
COPY --from=dashboard-builder /dashboard/dist ./sentinel/dashboard/dist

ENV GOOGLE_GENAI_USE_VERTEXAI=TRUE
ENV GOOGLE_CLOUD_LOCATION=global

EXPOSE 8080
CMD ["python", "-m", "sentinel.a2a.server"]