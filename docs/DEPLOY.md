# Deploy (CI/CD)

Simulated Studio runs as **one Cloud Run service** — FastAPI serves the built
React SPA, so a deploy always ships frontend + backend together.

## How deploys happen

`.github/workflows/deploy.yml` deploys to Cloud Run on:

1. **Merge to `develop`** — a PR merged into `develop` that touches app code
   (`backend/`, `frontend/`, `skills/`, `data/`, `Dockerfile`) auto-deploys.
2. **On demand** — any developer can open the repo's **Actions → deploy → Run
   workflow**, pick a component, and deploy.

Auth is **keyless** via Workload Identity Federation — GitHub exchanges a
short-lived OIDC token for GCP access. **No service-account key is stored in the
repo.**

## One-time setup

Run once by a project owner (creates the deployer identity + repo variables):

```bash
./scripts/setup-cicd.sh
```

It creates a least-privilege `gh-deployer` service account, a WIF pool/provider
scoped to this repo only, and sets these repo variables the workflow reads:
`GCP_WIF_PROVIDER`, `GCP_DEPLOY_SA`, `GCP_PROJECT_ID`, `GCP_REGION`,
`CLOUD_RUN_SERVICE`.

Roles granted to the deployer: `run.admin`, `cloudbuild.builds.editor`,
`artifactregistry.writer`, `storage.admin`, `serviceusage.serviceUsageConsumer`
(project) and `iam.serviceAccountUser` on the Cloud Run runtime SA only.

## Manual deploy (fallback)

```bash
./scripts/deploy_cloudrun.sh
```

## Note on separate frontend/backend deploys

Because one container serves both, the workflow's component choice
(`all`/`backend`/`frontend`) currently rebuilds the same service. To deploy them
independently, split into two Cloud Run services (static SPA + API) — a future
change if needed.
