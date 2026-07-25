# Deploy (CI/CD)

Two Cloud Run services:

| Service | Source | What it is |
| --- | --- | --- |
| `simulated-studio` | repo root | FastAPI + the built React SPA, one image |
| `story-genre-convertor` | `backend/story-genre-convertor/` | Standalone FastAPI, Gemini on Vertex AI |

## How deploys happen

Two entry points in **Actions**, split by what you changed:

| Workflow | Auto-runs on `develop` when | Manual run |
| --- | --- | --- |
| **deploy frontend** | `frontend/**` changes | Optional reason |
| **deploy backend** | `backend/**`, `skills/**`, `data/**`, `Dockerfile` changes | **Pick a service:** `all`, `simulated-studio`, or `story-genre-convertor` |

On a push, **deploy backend** works out which services to ship from the changed
paths, so a `backend/story-genre-convertor/` commit never rebuilds the studio
image and a `backend/app/` commit never touches the convertor. On a manual run
you choose. The plan appears in the run summary before anything deploys.

Both entry points share `.github/workflows/_deploy-studio.yml` — a reusable
workflow holding the studio build, since the SPA and the API ship in the same
container and must not drift apart. It also means a frontend deploy and a backend
deploy of the studio serialize on one concurrency group instead of racing.

Auth is **keyless** via Workload Identity Federation — GitHub exchanges a
short-lived OIDC token for GCP access. **No service-account key is stored in the
repo.**

## One-time setup

Run once by a project owner (creates the deployer identity + repo variables):

```bash
./scripts/setup-cicd.sh
```

It creates a least-privilege `gh-deployer` service account, a WIF pool/provider
scoped to this repo only, and sets these repo variables the workflows read:
`GCP_WIF_PROVIDER`, `GCP_DEPLOY_SA`, `GCP_PROJECT_ID`, `GCP_REGION`,
`CLOUD_RUN_SERVICE`, `GENRE_CONVERTOR_SERVICE`.

Roles granted to the deployer: `run.admin`, `cloudbuild.builds.editor`,
`artifactregistry.writer`, `storage.admin`, `serviceusage.serviceUsageConsumer`
(project) and `iam.serviceAccountUser` on the Cloud Run runtime SA only.

It also grants the Cloud Run **runtime** SA `roles/aiplatform.user` and enables
`aiplatform.googleapis.com` — the convertor calls Gemini through ADC, and the
deployer has no IAM-admin rights to grant that itself. Skip this and the deploy
succeeds while every conversion fails at the Vertex call.

## Manual deploy (fallback)

```bash
./scripts/deploy_cloudrun.sh                      # simulated-studio
(cd backend/story-genre-convertor && ./deploy.sh)  # story-genre-convertor
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

## What the frontend/backend split does and does not do

The **workflows** are separate; the studio **artifact** is not. `deploy frontend`
and a `simulated-studio` backend deploy build the same image, because the root
Dockerfile compiles the SPA into it. The split buys clearer triggers, separate
run history, and independent manual deploys — not independent artifacts. Truly
independent frontend deploys would mean a second Cloud Run service (or a bucket +
CDN) for static assets; not worth it yet.

`story-genre-convertor` **is** genuinely independent: its own directory,
Dockerfile, image, service, and Cloud Run flags.

## Known gap: the SPA cannot reach the convertor in production

`frontend/src/lib/genreApi.js` defaults to same-origin `/sgc`, which exists only
as a Vite dev proxy (`frontend/vite.config.js`). The deployed studio has no
`/sgc` route, so in production those calls fall through to the SPA catch-all.
Deploying the convertor does not fix this on its own. Two ways to close it:

1. Build the SPA with `VITE_SGC_URL=<convertor URL>` so it calls the service
   directly — works today: the convertor is deployed `--allow-unauthenticated`
   and its CORS defaults to `*`.
2. Add a real `/sgc` reverse proxy to `backend/app`, keeping one origin.
