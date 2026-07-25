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
echo "==> Enabling required APIs (aiplatform, firestore)…"
gcloud services enable \
  aiplatform.googleapis.com \
  firestore.googleapis.com \
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

# --- 4. Next steps ----------------------------------------------------------
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
