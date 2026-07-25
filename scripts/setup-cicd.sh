#!/usr/bin/env bash
#
# One-time setup for keyless CI/CD deploys (GitHub Actions -> Cloud Run) via
# Workload Identity Federation. Safe to re-run (idempotent).
#
# It creates a least-privilege deployer service account, a WIF pool/provider
# scoped to THIS repo, and sets the GitHub repo variables that the deploy
# workflows read (.github/workflows/deploy-frontend.yml, deploy-backend.yml).
# No JSON key is ever created.
#
# Requires: gcloud (authenticated as a project owner) and gh (authenticated).
# Usage:    ./scripts/setup-cicd.sh
set -euo pipefail

PROJECT="${PROJECT:-pocketfm-hackathon}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-simulated-studio}"
GENRE_SERVICE="${GENRE_SERVICE:-story-genre-convertor}"
REPO="${REPO:-ankitkumarsingh1702/pocketfm-hackathon}"
OWNER="${REPO%%/*}"
POOL="${POOL:-github-pool}"
PROVIDER="${PROVIDER:-github-provider}"
SA="${SA:-gh-deployer}"

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
SA_EMAIL="${SA}@${PROJECT}.iam.gserviceaccount.com"
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "==> Project ${PROJECT} (#${PROJECT_NUMBER}), repo ${REPO}"

echo "==> Enabling APIs"
gcloud services enable \
  iamcredentials.googleapis.com sts.googleapis.com iam.googleapis.com \
  run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  aiplatform.googleapis.com \
  --project "$PROJECT"

echo "==> Deployer service account"
gcloud iam service-accounts create "$SA" --project "$PROJECT" \
  --display-name "GitHub Actions deployer" 2>/dev/null || echo "    (already exists)"

echo "==> Least-privilege project roles"
for ROLE in \
  roles/run.admin \
  roles/cloudbuild.builds.editor \
  roles/artifactregistry.writer \
  roles/storage.admin \
  roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:${SA_EMAIL}" --role="$ROLE" \
    --condition=None >/dev/null
  echo "    granted ${ROLE}"
done

echo "==> Allow deployer to actAs the Cloud Run runtime SA (scoped to that SA only)"
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" --project "$PROJECT" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/iam.serviceAccountUser" \
  --condition=None >/dev/null

# The genre convertor calls Gemini on Vertex AI through ADC, so the runtime SA —
# not the deployer — is the identity that needs model access. Granted here
# because the deployer has no IAM-admin rights of its own.
echo "==> Allow the Cloud Run runtime SA to call Vertex AI"
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${RUNTIME_SA}" --role="roles/aiplatform.user" \
  --condition=None >/dev/null

echo "==> Workload Identity pool + OIDC provider (scoped to ${OWNER})"
gcloud iam workload-identity-pools create "$POOL" --project "$PROJECT" \
  --location=global --display-name="GitHub Actions" 2>/dev/null || echo "    (pool exists)"
gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
  --project "$PROJECT" --location=global --workload-identity-pool="$POOL" \
  --display-name="GitHub OIDC" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
  --attribute-condition="assertion.repository_owner=='${OWNER}'" 2>/dev/null \
  || echo "    (provider exists)"

echo "==> Bind the deployer SA to THIS repo only"
MEMBER="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/attribute.repository/${REPO}"
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" --project "$PROJECT" \
  --role="roles/iam.workloadIdentityUser" --member="$MEMBER" --condition=None >/dev/null

PROVIDER_RESOURCE="$(gcloud iam workload-identity-pools providers describe "$PROVIDER" \
  --project "$PROJECT" --location=global --workload-identity-pool="$POOL" \
  --format='value(name)')"

echo "==> Setting GitHub repo variables"
gh variable set GCP_WIF_PROVIDER  --repo "$REPO" --body "$PROVIDER_RESOURCE"
gh variable set GCP_DEPLOY_SA     --repo "$REPO" --body "$SA_EMAIL"
gh variable set GCP_PROJECT_ID    --repo "$REPO" --body "$PROJECT"
gh variable set GCP_REGION        --repo "$REPO" --body "$REGION"
gh variable set CLOUD_RUN_SERVICE --repo "$REPO" --body "$SERVICE"
gh variable set GENRE_CONVERTOR_SERVICE --repo "$REPO" --body "$GENRE_SERVICE"

echo ""
echo "Done. CI/CD is ready:"
echo "  WIF provider: ${PROVIDER_RESOURCE}"
echo "  Deployer SA:  ${SA_EMAIL}"
echo "  Services:     ${SERVICE}, ${GENRE_SERVICE}"
echo "  Next: merge the deploy workflows to develop, or run them from the Actions"
echo "        tab — 'deploy frontend', or 'deploy backend' (pick a service)."
