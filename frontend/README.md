# Simulated Studio

**One persona-simulation engine, many lenses** — built for a PocketFM hackathon.

Simulated Studio simulates a representative panel of listeners (and expert
critics) reacting to an audio-drama episode, then views those reactions through
different **lenses**:

- **Audience Simulator** — fan out a story to a panel of listener personas and
  measure binge rate, hook score, a stage-by-stage retention curve, and the top
  reasons people drop off — segmented by audience type.
- **Writers Room** — a panel of expert-critic personas gives craft feedback
  (verdict, score, strengths, issues, a concrete fix) plus a local consensus.
- **Cliffhanger Optimizer** — rewrite a weak ending into a gripping cliffhanger
  and A/B test it against the original with the audience panel to measure lift.

All three are thin lenses over **one** persona-simulation engine running on
**Google Vertex AI** — Gemini by default, Claude optional — with results
optionally persisted to Firestore.

## Repo layout

```
.
├── frontend/     # React + Vite (JavaScript) UI — StudioPanel + API client
├── backend/      # FastAPI engine, lenses, Vertex LLM clients, Firestore (uv)
├── skills/       # Persona / agent definitions (YAML) — audience + experts
├── data/         # Sample stories (e.g. "Andhera" episodes)
└── scripts/      # gcp_setup.sh and other tooling
```

## Quickstart

### 0. GCP / ADC (one-time)

All Vertex AI + Firestore access uses **Application Default Credentials** — no
keys in the repo.

```bash
gcloud auth application-default login
./scripts/gcp_setup.sh <your-project-id>   # enables APIs + creates Firestore
```

`scripts/gcp_setup.sh` is idempotent — safe to re-run.

### 1. Backend (FastAPI, via uv)

```bash
cd backend
cp .env.example .env                                # optional overrides
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Health check: http://localhost:8000/health · full details in
[`backend/README.md`](backend/README.md) (endpoints, config, Gemini ⇄ Claude).

### 2. Frontend (React + Vite)

```bash
cp frontend/.env.example frontend/.env              # VITE_API_URL -> backend
npm --prefix frontend install
npm --prefix frontend run dev
```

Open the printed URL (default http://localhost:5173). The **Simulated Studio**
panel at the top of the page shows backend health and runs the Audience
Simulator against the backend.

Frontend scripts: `dev`, `build`, `preview`, `lint`.

---

## Team workflow (3 devs)

We use a simple two-branch flow. **`develop` is the default branch — all work merges here first.**

- **`main`** — stable / demo-ready. Never push directly.
- **`develop`** — integration branch. **All PRs target `develop`.**

### Commit hygiene (enforced)

Commits and PRs must not carry AI-assistant **attribution** — no
`Co-Authored-By: Claude/Anthropic`, no "Generated with …", no 🤖. (Mentioning
Claude/Gemini as a *model choice* is fine; only authorship attribution is
blocked.) Enforced two ways:

- **Local git hook** — run once after cloning: `./scripts/setup-hooks.sh`
  (points `core.hooksPath` at `.githooks`; the `commit-msg` hook rejects
  offending messages before they land).
- **CI** — the `no-ai-attribution` workflow re-scans every PR's commits, title,
  and body against `develop`/`main`, so it can't be bypassed locally.

### Day-to-day

1. Always branch off the latest `develop`:
   ```bash
   git checkout develop
   git pull
   git checkout -b feat/<your-name>/<short-description>
   ```
2. Commit your work and push the branch:
   ```bash
   git push -u origin feat/<your-name>/<short-description>
   ```
3. Open a Pull Request **into `develop`** (it's the default base, so this is automatic):
   ```bash
   gh pr create --base develop --fill
   ```
4. Get **1 review** from another dev, then squash-merge into `develop`.
5. When `develop` is stable (e.g. before the demo), we merge `develop` → `main` via a PR.

### Rules of thumb

- One feature = one branch = one PR. Keep PRs small.
- Never commit directly to `main` or `develop` — always go through a PR.
- Pull `develop` before starting new work to avoid conflicts.
- Branch names: `feat/...`, `fix/...`, `chore/...`.

> Note: This is a private repo on a free plan, so GitHub's automatic branch
> protection isn't available. The rules above are enforced by team convention.
> If we upgrade to GitHub Pro (free via GitHub Education) or make the repo
> public, we can enforce "PR + 1 review required" automatically.

---

## Vite / React notes

This project uses [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react) with [Oxlint](https://oxc.rs).

- **React Compiler** is not enabled by default (impacts dev/build perf). To add it, see the [docs](https://react.dev/learn/react-compiler/installation).
- For a production app, consider the [TypeScript template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) with type-aware lint rules.
