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

## Knowledge graph (Neo4j) — optional

The **Story Canon** knowledge graph gives the agents shared, persistent memory.
It is entirely optional: with no credentials the app runs exactly as before with
an empty canon (graceful degradation). To turn it on:

1. Create a **Neo4j Aura** instance (a free tier on GCP is fine) and note its
   `NEO4J_URI` (`neo4j+s://…`), username, and password.
2. Store them in Secret Manager and grant the Cloud Run runtime SA access — this
   is scripted; just export the values and run the setup once:

   ```bash
   export NEO4J_URI='neo4j+s://xxxx.databases.neo4j.io'
   export NEO4J_USERNAME='neo4j'
   export NEO4J_PASSWORD='••••••••'
   ./scripts/gcp_setup.sh
   ```

3. Deploy. Both `deploy_cloudrun.sh` and the GitHub Actions workflow **auto-mount
   the secrets when they exist** (`--set-secrets NEO4J_URI/USERNAME/PASSWORD`)
   and skip them otherwise, so a graph-less deploy still works unchanged.

Confirm it is live: `GET /health` shows `"graph": {"configured": true, …}` and
`GET /api/canon/health` returns `{"online": true}`.

> No Neo4j credentials ever live in the repo — only in Secret Manager, mounted
> as env vars at runtime, mirroring the ADC/no-keys model used for Vertex AI.

## Note on separate frontend/backend deploys

Because one container serves both, the workflow's component choice
(`all`/`backend`/`frontend`) currently rebuilds the same service. To deploy them
independently, split into two Cloud Run services (static SPA + API) — a future
change if needed.
