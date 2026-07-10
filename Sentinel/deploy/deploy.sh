#!/bin/bash
set -euo pipefail
PROJECT_ID="recruiter-sergiu-260213"
REGION="us-central1"
IMAGE="gcr.io/$PROJECT_ID/sentinel:latest"

# Build from the Sentinel repo root so requirements.txt and the sentinel/
# package are in the build context. This script lives in deploy/, so the
# root is its parent directory.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

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
  --image $IMAGE \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --project $PROJECT_ID
