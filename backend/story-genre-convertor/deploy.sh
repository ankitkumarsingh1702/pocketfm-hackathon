#!/usr/bin/env bash
set -euo pipefail

# Deploy the genre converter to Cloud Run as a standalone service.
#
# Auth is ADC end to end: locally it is your gcloud login, on Cloud Run it is the
# runtime service account, which needs roles/aiplatform.user. No API keys.
#
# Usage: ./deploy.sh [PROJECT]

PROJECT="${1:-${PROJECT:-pocketfm-hackathon}}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-story-genre-convertor}"

echo "==> Project: ${PROJECT}"
echo "==> Region:  ${REGION}"
echo "==> Service: ${SERVICE}"

echo "==> Enabling required APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  aiplatform.googleapis.com \
  --project "${PROJECT}"

# Why these flags, since none of them are the default:
#
#   --min-instances 1      Jobs run on background threads. Scaling to zero
#                          mid-conversion would kill work nobody is waiting on.
#   --max-instances 1      Job state is a process-local dict, so a poll that
#                          landed on a second instance would 404.
#   --no-cpu-throttling    Cloud Run throttles CPU outside request handling by
#                          default, which would stall a background job between
#                          polls. This is the flag that makes async work at all.
#   --timeout 300          Requests return immediately; only uploads need time.
#   --concurrency 40       Polls are cheap; the work is bounded by the pool.
#
# min-instances 1 + no-cpu-throttling means always-on billing for one small
# instance. That is the price of a 6-minute job on a request-driven platform.
echo "==> Deploying from source..."
gcloud run deploy "${SERVICE}" \
  --source . \
  --region "${REGION}" \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 1 \
  --max-instances 1 \
  --no-cpu-throttling \
  --concurrency 40 \
  --timeout 300 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=${PROJECT},VERTEX_LOCATION=${REGION},GEMINI_MODEL=gemini-2.5-pro,CACHE_DIR=/tmp/sgc-cache" \
  --project "${PROJECT}"

URL="$(gcloud run services describe "${SERVICE}" \
  --region "${REGION}" --project "${PROJECT}" --format 'value(status.url)')"

echo
echo "==> Deployed: ${URL}"
echo
echo "    curl ${URL}/health"
echo "    curl ${URL}/api/genres"
echo "    curl -X POST ${URL}/api/convert -H 'Content-Type: application/json' \\"
echo "         -d '{\"genre\":\"horror\",\"text\":\"...\"}'"
echo "    curl ${URL}/api/jobs/<job_id>"
