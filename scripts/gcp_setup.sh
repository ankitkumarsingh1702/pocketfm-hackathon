#!/usr/bin/env bash
#
# gcp_setup.sh — one-time (idempotent) GCP setup for Simulated Studio.
#
# Enables the Vertex AI + Firestore APIs, points ADC at your project, and
# creates a native-mode Firestore database if one doesn't already exist.
# Safe to re-run: every step checks current state before changing anything.
#
# Usage:
#   ./scripts/gcp_setup.sh [PROJECT_ID]
#
# If PROJECT_ID is omitted, the active `gcloud config` project is used.
#
# Prereqs: gcloud CLI installed and `gcloud auth login` already done.

set -euo pipefail

# --- Config -----------------------------------------------------------------
# Firestore location. nam5 = US multi-region. Change if you need another.
FIRESTORE_LOCATION="nam5"

# --- 0. Resolve the project -------------------------------------------------
# Prefer the CLI arg; otherwise fall back to the active gcloud config project.
PROJECT="${1:-$(gcloud config get-value project 2>/dev/null || true)}"
if [[ -z "${PROJECT}" || "${PROJECT}" == "(unset)" ]]; then
  echo "ERROR: No project specified and no active gcloud project is set." >&2
  echo "       Pass one explicitly:  ./scripts/gcp_setup.sh my-project-id" >&2
  exit 1
fi
echo "==> Using project: ${PROJECT}"
gcloud config set project "${PROJECT}" >/dev/null

# --- 1. Enable required APIs (enable is a no-op if already enabled) ----------
echo "==> Enabling required APIs (aiplatform, firestore, secretmanager)…"
gcloud services enable \
  aiplatform.googleapis.com \
  firestore.googleapis.com \
  secretmanager.googleapis.com \
  --project "${PROJECT}"

# --- 2. Point Application Default Credentials at this project ----------------
# Sets the ADC quota/billing project so Vertex + Firestore client libs bill
# and quota-check against the right project. Assumes you've already run
# `gcloud auth application-default login`.
echo "==> Setting ADC quota project to ${PROJECT}…"
if ! gcloud auth application-default set-quota-project "${PROJECT}" 2>/dev/null; then
  echo "    (!) Could not set the ADC quota project."
  echo "        Run 'gcloud auth application-default login' first, then re-run."
fi

# --- 3. Create a native-mode Firestore database if none exists --------------
# A project has at most one (default) database. Detect it before creating so
# re-runs don't error out.
echo "==> Checking for an existing Firestore database…"
if gcloud firestore databases describe --database="(default)" --project "${PROJECT}" >/dev/null 2>&1; then
  echo "    Firestore (default) database already exists — skipping create."
else
  echo "    None found. Creating native-mode database in ${FIRESTORE_LOCATION}…"
  gcloud firestore databases create \
    --location="${FIRESTORE_LOCATION}" \
    --type=firestore-native \
    --project "${PROJECT}"
fi

# --- 4. (Optional) Neo4j knowledge-graph secrets ----------------------------
# The story-canon knowledge graph is optional. If you have a Neo4j instance
# (e.g. a free Neo4j Aura DB on GCP), export its details before running this
# script and they'll be stored in Secret Manager for Cloud Run to mount:
#
#   export NEO4J_URI='neo4j+s://xxxx.databases.neo4j.io'
#   export NEO4J_USERNAME='neo4j'
#   export NEO4J_PASSWORD='••••••••'
#   ./scripts/gcp_setup.sh
#
# Nothing here touches the repo — credentials live only in Secret Manager.
if [[ -n "${NEO4J_URI:-}" && -n "${NEO4J_PASSWORD:-}" ]]; then
  echo "==> Storing Neo4j credentials in Secret Manager…"
  _upsert_secret() {
    local name="$1" value="$2"
    if gcloud secrets describe "${name}" --project "${PROJECT}" >/dev/null 2>&1; then
      printf '%s' "${value}" | gcloud secrets versions add "${name}" --data-file=- --project "${PROJECT}" >/dev/null
    else
      printf '%s' "${value}" | gcloud secrets create "${name}" \
        --data-file=- --replication-policy=automatic --project "${PROJECT}" >/dev/null
    fi
  }
  _upsert_secret NEO4J_URI "${NEO4J_URI}"
  _upsert_secret NEO4J_USERNAME "${NEO4J_USERNAME:-neo4j}"
  _upsert_secret NEO4J_PASSWORD "${NEO4J_PASSWORD}"

  # Grant the Cloud Run runtime (default compute) SA read access to the secrets.
  PROJ_NUM="$(gcloud projects describe "${PROJECT}" --format='value(projectNumber)')"
  RUNTIME_SA="${PROJ_NUM}-compute@developer.gserviceaccount.com"
  for name in NEO4J_URI NEO4J_USERNAME NEO4J_PASSWORD; do
    gcloud secrets add-iam-policy-binding "${name}" \
      --member="serviceAccount:${RUNTIME_SA}" \
      --role="roles/secretmanager.secretAccessor" \
      --project "${PROJECT}" >/dev/null 2>&1 || true
  done
  echo "    Neo4j secrets stored and runtime SA (${RUNTIME_SA}) granted access."
else
  echo "==> Skipping Neo4j secrets (NEO4J_URI/NEO4J_PASSWORD not set) — the"
  echo "    knowledge graph stays off and the app runs with an empty canon."
fi

# --- 4b. (Optional) Sarvam API key (AI Producer) ----------------------------
# The AI Producer lens calls Sarvam (LLM + bulbul:v3 TTS). Export the key before
# running to store it in Secret Manager for Cloud Run to mount:
#
#   export SARVAM_API_KEY='sk_...'
#   ./scripts/gcp_setup.sh
#
# Nothing here touches the repo — the key lives only in Secret Manager. Without
# it the studio still runs; only the AI Producer tab returns 503.
if [[ -n "${SARVAM_API_KEY:-}" ]]; then
  echo "==> Storing Sarvam API key in Secret Manager…"
  if gcloud secrets describe SARVAM_API_KEY --project "${PROJECT}" >/dev/null 2>&1; then
    printf '%s' "${SARVAM_API_KEY}" | gcloud secrets versions add SARVAM_API_KEY --data-file=- --project "${PROJECT}" >/dev/null
  else
    printf '%s' "${SARVAM_API_KEY}" | gcloud secrets create SARVAM_API_KEY \
      --data-file=- --replication-policy=automatic --project "${PROJECT}" >/dev/null
  fi
  PROJ_NUM="$(gcloud projects describe "${PROJECT}" --format='value(projectNumber)')"
  RUNTIME_SA="${PROJ_NUM}-compute@developer.gserviceaccount.com"
  gcloud secrets add-iam-policy-binding SARVAM_API_KEY \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role="roles/secretmanager.secretAccessor" \
    --project "${PROJECT}" >/dev/null 2>&1 || true
  echo "    Sarvam API key stored and runtime SA (${RUNTIME_SA}) granted access."
else
  echo "==> Skipping Sarvam API key (SARVAM_API_KEY not set) — the AI Producer"
  echo "    tab returns 503 until the key is stored in Secret Manager."
fi

# --- 5. Next steps ----------------------------------------------------------
cat <<EOF

============================================================
 Simulated Studio — GCP setup complete for: ${PROJECT}
============================================================

Next steps:

  1. Make sure ADC is logged in (if you haven't already):
       gcloud auth application-default login

  2. Configure the backend:
       cd backend
       cp .env.example .env      # set GOOGLE_CLOUD_PROJECT=${PROJECT}
       uv sync
       uv run uvicorn app.main:app --reload --port 8000

  3. (Optional) To use Claude instead of Gemini, enable the Claude models in
     Vertex AI Model Garden, then set LLM_PROVIDER=claude in backend/.env.

  4. Run the frontend:
       npm --prefix frontend install
       npm --prefix frontend run dev

Health check:  http://localhost:8000/health
============================================================
EOF
