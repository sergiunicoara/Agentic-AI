#!/bin/bash
set -euo pipefail
PROJECT_ID="recruiter-sergiu-260213"
REGION="us-central1"
IMAGE="gcr.io/$PROJECT_ID/sentinel:latest"

# Build from the Sentinel repo root so requirements.txt and the sentinel/
# package are in the build context. This script lives in deploy/, so the
# root is its parent directory.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

docker build -f "$ROOT_DIR/deploy/Dockerfile" -t "$IMAGE" "$ROOT_DIR"
docker push "$IMAGE"

gcloud run deploy sentinel \
  --image $IMAGE \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --project $PROJECT_ID