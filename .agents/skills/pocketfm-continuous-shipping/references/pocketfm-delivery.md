# PocketFM delivery reference

## Repository contract

- Repository: `ankitkumarsingh1702/pocketfm-hackathon`
- Integration branch: `develop`
- GCP project: `pocketfm-hackathon`
- Region: `us-central1`
- Studio service: `simulated-studio`
- Convertor service: `story-genre-convertor`
- UI source of truth: `.agents/skills/pocketfm-ui-design/SKILL.md`
- Commit and PR text must pass `.github/workflows/no-ai-attribution.yml`.

The Simulated Studio frontend and backend are one artifact. The root Dockerfile
builds Vite with Node 20/npm 11, copies the result into the FastAPI image, and
FastAPI serves the SPA. A "frontend deploy" therefore rebuilds and deploys the
same `simulated-studio` Cloud Run service as a Studio backend deploy.

The Story Genre Convertor is independent. It has its own directory, Dockerfile,
runtime flags, and Cloud Run service.

## Read-only preflight

Run from the repository root:

```bash
git status --short --branch
git worktree list
git fetch --prune origin
git rev-parse HEAD
git rev-parse origin/develop
git rev-list --left-right --count HEAD...origin/develop
git diff --name-only
git diff --cached --name-only
git diff --name-only origin/develop...HEAD
gh pr list --repo ankitkumarsingh1702/pocketfm-hackathon --state open
```

Before creating a worktree, verify the proposed branch and directory do not
exist. Create the isolated worktree from `origin/develop`, not from a dirty local
branch:

```bash
git worktree add -b codex/<scope> <explicit-unique-directory> origin/develop
```

Claude should use `claude/<scope>`. Never reuse another agent's branch or
worktree.

## Validation matrix

### Frontend

```bash
cd frontend
npm ci
npm run lint
npm run build
npx -y npm@11.18.0 ci --dry-run
```

Use the repository UI skill and visually inspect relevant desktop/mobile,
loading, error, empty, focus, and reduced-motion behavior.

### Simulated Studio backend

```bash
cd backend
uv sync --locked
uv run pytest -q
USE_FIRESTORE=false uv run uvicorn app.main:app --host 127.0.0.1 --port <free-port>
```

Smoke `GET /health`, `GET /api/personas`, and `GET /openapi.json`. Avoid paid
simulation endpoints unless the task requires a real model call.

Python bytecode and `.cache` files are generated artifacts. Do not stage them.
If the repository still tracks historical copies, restore only copies changed
by the current test process before committing.

### Story Genre Convertor

From `backend/story-genre-convertor`:

```bash
python verify.py --selftest
python transform.py --selftest
python -m py_compile api.py pipeline.py
```

Cold `calibrate.py` and conversion runs call Gemini and are not default smoke
tests. After deployment verify both `GET /health` and `GET /api/genres`.

## Deploy lane mapping

| Changed paths | Workflow | Service deployed |
| --- | --- | --- |
| `frontend/**` | `deploy-frontend.yml` | `simulated-studio` |
| `backend/**` excluding convertor, `skills/**`, `data/**`, root `Dockerfile` | `deploy-backend.yml` | `simulated-studio` |
| `backend/story-genre-convertor/**` | `deploy-backend.yml` | `story-genre-convertor` |
| Both backend scopes | `deploy-backend.yml` | both services |
| Docs and agent skills only | none | no app deploy |

Both frontend and Studio backend entry points call
`.github/workflows/_deploy-studio.yml`. Its shared
`deploy-simulated-studio` concurrency group has `cancel-in-progress: false`;
allow queued deploys to serialize.

Pushes to `develop` trigger the appropriate workflow automatically. To recover
or intentionally redeploy:

```bash
gh workflow run deploy-frontend.yml \
  --repo ankitkumarsingh1702/pocketfm-hackathon \
  --ref develop \
  -f reason='<concise reason>'

gh workflow run deploy-backend.yml \
  --repo ankitkumarsingh1702/pocketfm-hackathon \
  --ref develop \
  -f service=simulated-studio \
  -f reason='<concise reason>'

gh workflow run deploy-backend.yml \
  --repo ankitkumarsingh1702/pocketfm-hackathon \
  --ref develop \
  -f service=story-genre-convertor \
  -f reason='<concise reason>'
```

Use `service=all` only when both independent services genuinely need a redeploy.

## Deployment proof

Find and watch the run for the merge commit:

```bash
gh run list \
  --repo ankitkumarsingh1702/pocketfm-hackathon \
  --branch develop \
  --limit 10

gh run view <run-id> \
  --repo ankitkumarsingh1702/pocketfm-hackathon \
  --json headSha,status,conclusion,jobs,url

gh run watch <run-id> \
  --repo ankitkumarsingh1702/pocketfm-hackathon \
  --exit-status
```

Verify the relevant Cloud Run service:

```bash
gcloud run services describe <service> \
  --project pocketfm-hackathon \
  --region us-central1 \
  --format='yaml(status.url,status.latestReadyRevisionName,status.latestCreatedRevisionName,status.traffic)'
```

Require `latestReadyRevisionName == latestCreatedRevisionName` and 100% traffic
to the intended revision. Curl the reported service URL, not a remembered URL.

For `simulated-studio`, verify:

```text
GET /health
GET /
GET /api/personas
```

For `story-genre-convertor`, verify:

```text
GET /health
GET /api/genres
```

For frontend changes, confirm the live HTML references the new assets and
visually exercise the changed interaction. A successful API health response is
not proof that the new frontend is browser-visible.

## Truthful handoff template

Report:

```text
Source: <branch> @ <feature SHA>, tests <result>
PR: <number/state>, targets develop
Merge: <merge SHA or not merged>
Deploy: <workflow/run/conclusion/headSha>
Runtime: <service/revision/traffic>
Live: <URL and verified routes/interactions>
Blocked: <none or one exact external prerequisite>
```
