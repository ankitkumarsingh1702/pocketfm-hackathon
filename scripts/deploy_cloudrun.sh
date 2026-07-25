#!/usr/bin/env bash
set -euo pipefail

# Deploy Simulated Studio (FastAPI + built React frontend, single container) to Cloud Run.
#
# The runtime service account needs:
#   - roles/aiplatform.user   (Vertex AI calls)
#   - roles/datastore.user    (Firestore persistence)
# (already granted; no action needed here).
#
# Usage: ./scripts/deploy_cloudrun.sh [PROJECT]
#   PROJECT may also come from the environment; the positional arg wins.

PROJECT="${1:-${PROJECT:-pocketfm-hackathon}}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-simulated-studio}"

echo "==> Project: ${PROJECT}"
echo "==> Region:  ${REGION}"
echo "==> Service: ${SERVICE}"

echo "==> Enabling required Google Cloud APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  --project "${PROJECT}"

# Mount Neo4j knowledge-graph credentials from Secret Manager, but only if the
# secrets exist — a graph-less deploy still works (the app degrades gracefully).
SECRET_FLAGS=()
if gcloud secrets describe NEO4J_URI --project "${PROJECT}" >/dev/null 2>&1; then
  SECRET_FLAGS+=(--set-secrets "NEO4J_URI=NEO4J_URI:latest,NEO4J_USERNAME=NEO4J_USERNAME:latest,NEO4J_PASSWORD=NEO4J_PASSWORD:latest")
  echo "==> Mounting Neo4j secrets from Secret Manager."
else
  echo "==> No NEO4J_URI secret found — deploying without the knowledge graph."
fi

echo "==> Deploying ${SERVICE} to Cloud Run from source..."
gcloud run deploy "${SERVICE}" \
  --source . \
  --region "${REGION}" \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --set-env-vars GOOGLE_CLOUD_PROJECT="${PROJECT}" \
  ${SECRET_FLAGS[@]+"${SECRET_FLAGS[@]}"} \
  --project "${PROJECT}"

echo "==> Deployment complete. Service URL:"
gcloud run services describe "${SERVICE}" \
  --region "${REGION}" \
  --project "${PROJECT}" \
  --format 'value(status.url)'
