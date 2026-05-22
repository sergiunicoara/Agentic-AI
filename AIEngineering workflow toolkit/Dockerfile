# ── Stage 1: Build React UI ───────────────────────────────────────────────────
FROM node:20-slim AS ui-builder
WORKDIR /app/ui
COPY ui/package*.json ./
RUN npm ci --silent
COPY ui/ ./
RUN npm run build

# ── Stage 2: Python runtime ───────────────────────────────────────────────────
FROM python:3.11-slim AS runtime
WORKDIR /app

# Install linter CLI tools expected on PATH by the MCP server
RUN pip install --no-cache-dir ruff mypy bandit

# Copy project metadata first (layer cache-friendly)
COPY pyproject.toml ./

# Copy Python source
COPY main.py ./
COPY api/        ./api/
COPY orchestrator/ ./orchestrator/
COPY review_agent/ ./review_agent/
COPY subagents/  ./subagents/
COPY skills/     ./skills/
COPY eval/       ./eval/
COPY observability/ ./observability/
COPY mcp_server/ ./mcp_server/

# Install all Python deps (core + ui extras)
RUN pip install --no-cache-dir -e ".[ui]"

# Copy built React assets from stage 1
COPY --from=ui-builder /app/ui/dist ./ui/dist

EXPOSE 8000

CMD ["python", "main.py", "ui", "--host", "0.0.0.0", "--port", "8000"]
