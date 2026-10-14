#!/bin/bash
set -euo pipefail
PROJECT_ID="recruiter-sergiu-260213"
REGION="us-central1"
# Build from the Sentinel repo root so requirements.txt and the sentinel/
# package are in the build context. This script lives in deploy/, so the
# root is its parent directory.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Tag by commit so every deploy is traceable and rollbacks are exact
# (":latest" made it impossible to tell which code a revision ran).
IMAGE_TAG="$(git -C "$ROOT_DIR" rev-parse --short HEAD)"
if [ -n "$(git -C "$ROOT_DIR" status --porcelain -- sentinel deploy requirements.txt)" ]; then
  IMAGE_TAG="${IMAGE_TAG}-dirty-$(date +%Y%m%d%H%M%S)"
fi
IMAGE="gcr.io/$PROJECT_ID/sentinel:$IMAGE_TAG"

# The service is publicly reachable (--allow-unauthenticated, so other
# agents can call it), which makes app-level auth mandatory: the server
# refuses to start on Cloud Run without SENTINEL_A2A_TOKEN. Both secrets
# must exist in Secret Manager before deploying:
#   printf '%s' "$(openssl rand -hex 32)" | gcloud secrets create sentinel-a2a-token --data-file=- --project $PROJECT_ID
#   printf '%s' "$(openssl rand -hex 32)" | gcloud secrets create sentinel-signing-key --data-file=- --project $PROJECT_ID
for secret in sentinel-a2a-token sentinel-signing-key; do
  if ! gcloud secrets describe "$secret" --project "$PROJECT_ID" >/dev/null 2>&1; then
    echo "Missing Secret Manager secret '$secret' — see the comment above for how to create it." >&2
    exit 1
  fi
done

if [ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" ] && [ -f "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
  gcloud auth activate-service-account --key-file="$GOOGLE_APPLICATION_CREDENTIALS" --quiet
else
  ACTIVE_ACCOUNT="$(gcloud auth list --format='value(account)' 2>/dev/null | head -n 1 || true)"
  if [ -n "$ACTIVE_ACCOUNT" ]; then
    gcloud config set account "$ACTIVE_ACCOUNT" --quiet >/dev/null
  fi
fi

export DOCKER_CONFIG="$(mktemp -d)"
trap 'rm -rf "$DOCKER_CONFIG"' EXIT

gcloud auth print-access-token | docker login -u oauth2accesstoken --password-stdin https://gcr.io > /dev/null 2>&1
docker build -f "$ROOT_DIR/deploy/Dockerfile" -t "$IMAGE" "$ROOT_DIR"
docker push "$IMAGE"

gcloud run deploy sentinel \
  --image "$IMAGE" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --set-secrets "SENTINEL_A2A_TOKEN=sentinel-a2a-token:latest,SENTINEL_SIGNING_KEY=sentinel-signing-key:latest" \
  --project "$PROJECT_ID"

# The agent card must advertise the real service URL, not the localhost
# default. It's only known after the first deploy, so set it afterwards
# (a no-op revision when it's already correct).
SERVICE_URL="$(gcloud run services describe sentinel --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)')"
gcloud run services update sentinel \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --update-env-vars "SENTINEL_PUBLIC_URL=$SERVICE_URL"
