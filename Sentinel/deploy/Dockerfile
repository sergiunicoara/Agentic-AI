# Stage 1: build the React dashboard
FROM node:20-bookworm-slim AS dashboard-builder
WORKDIR /dashboard
COPY sentinel/dashboard/package*.json ./
RUN npm ci
COPY sentinel/dashboard/ .
RUN npm run build

# Stage 2: Python runtime
FROM python:3.11-slim-bookworm

# Build context is the Sentinel repo root (see deploy/deploy.sh):
#   docker build -f deploy/Dockerfile .
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# Run as an unprivileged user: scans execute third-party tools over
# caller-chosen targets, so a compromise should not get root in the container.
RUN useradd --create-home --uid 10001 sentinel
USER sentinel

# Pre-fetch semgrep's registry rule packs (p/python, p/gitleaks) into the
# image at build time, when network access is reliable. Without this,
# every fresh Cloud Run container (ephemeral filesystem — no cache
# survives between instances) fetches these packs on its first scan,
# which can silently exceed the ~30s idle-WebSocket timeout Cloud Run's
# front end enforces (semgrep_scan itself allows up to 120s, but nothing
# streams progress during that fetch, so the socket looks idle and gets
# dropped before the scan can finish). Baking the cache in removes the
# runtime network dependency entirely — scans are faster and the
# dashboard's live WebSocket never goes silent long enough to be killed.
# Runs as the `sentinel` user so the cache lands in that user's home. A
# failed fetch doesn't fail the build (network can be flaky), but it is
# reported loudly instead of being swallowed.
RUN semgrep --config=p/python --config=p/gitleaks --metrics=off --quiet /app \
    || echo "WARNING: semgrep registry pack prefetch failed; first scan will fetch at runtime" >&2

# .dockerignore keeps .env, .git, caches and tests out of this layer.
COPY . .

# Drop the React build output into a location the server can serve.
COPY --from=dashboard-builder /dashboard/dist ./sentinel/dashboard/dist

ENV GOOGLE_GENAI_USE_VERTEXAI=TRUE
ENV GOOGLE_CLOUD_LOCATION=global

EXPOSE 8080
CMD ["python", "-m", "sentinel.a2a.server"]