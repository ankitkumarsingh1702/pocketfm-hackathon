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

echo "==> Deploying ${SERVICE} to Cloud Run from source..."
gcloud run deploy "${SERVICE}" \
  --source . \
  --region "${REGION}" \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --set-env-vars GOOGLE_CLOUD_PROJECT="${PROJECT}" \
  --project "${PROJECT}"

echo "==> Deployment complete. Service URL:"
gcloud run services describe "${SERVICE}" \
  --region "${REGION}" \
  --project "${PROJECT}" \
  --format 'value(status.url)'
