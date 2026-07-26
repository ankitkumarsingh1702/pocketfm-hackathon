# Simulated Studio — Backend

FastAPI service that powers the **persona-simulation engine** and its lenses
(Audience Simulator, Writers Room, Cliffhanger Optimizer), running on
**Google Vertex AI** (Gemini by default, Claude optional) with optional
Firestore persistence.

Python package rooted at `app/` (import prefix `app.`). Managed with
[uv](https://docs.astral.sh/uv/).

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- A GCP project with Vertex AI enabled, and **ADC** configured:
  ```bash
  gcloud auth application-default login
  ```
  One-time project setup (enable APIs + create Firestore) is scripted in
  [`../scripts/gcp_setup.sh`](../scripts/gcp_setup.sh).

## Run it

From the `backend/` directory:

```bash
uv sync                                             # install locked deps
cp .env.example .env                                # optional: override defaults
uv run uvicorn app.main:app --reload --port 8000
```

The API is now at http://localhost:8000 — check http://localhost:8000/health.

## Configuration

All settings live in `app/config.py` and are overridable via `backend/.env`
(or the environment). See [`.env.example`](.env.example) for the full,
commented list. Key ones:

| Env var                 | Default                      | Purpose                                   |
| ----------------------- | ---------------------------- | ----------------------------------------- |
| `GOOGLE_CLOUD_PROJECT`  | `hushh-pda-uat`              | GCP project hosting Vertex AI / Firestore |
| `VERTEX_LOCATION`       | `us-central1`                | Region for Gemini-on-Vertex              |
| `LLM_PROVIDER`          | `gemini`                     | `gemini` or `claude`                      |
| `GEMINI_MODEL`          | `gemini-3.6-flash`           | Gemini model id                           |
| `CLAUDE_MODEL`          | `claude-haiku-4-5@20251001`  | Claude-on-Vertex model id (dated form)    |
| `CLAUDE_LOCATION`       | `us-east5`                   | Region for Claude-on-Vertex               |
| `USE_FIRESTORE`         | `true`                       | Persist runs to Firestore (graceful off)  |
| `AUDIENCE_FANOUT`       | `60`                         | Listeners simulated per audience run      |
| `CORS_ORIGINS`          | `http://localhost:5173,…4173`| Allowed frontend origins                  |

Auth is **always ADC** — no keys are stored in the repo.

## Switching provider (Gemini ⇄ Claude)

The provider is chosen at runtime by `LLM_PROVIDER` (via `app/llm/factory.py`).

- **Gemini** (default) — works in any GCP project with Vertex AI enabled:
  ```bash
  LLM_PROVIDER=gemini uv run uvicorn app.main:app --reload --port 8000
  ```
- **Claude** — requires the Claude models to be enabled in Vertex AI Model
  Garden, and a region that offers them (default `us-east5`):
  ```bash
  LLM_PROVIDER=claude uv run uvicorn app.main:app --reload --port 8000
  ```

Or set the value in `backend/.env` and just run `uv run uvicorn app.main:app --reload --port 8000`.

## Endpoints

| Method | Path                         | Body                  | Returns             |
| ------ | ---------------------------- | --------------------- | ------------------- |
| GET    | `/health`                    | —                     | provider/project/location/firestore status |
| GET    | `/api/personas`              | —                     | `{ audience[], experts[] }` |
| POST   | `/api/simulate/audience`     | `SimulateRequest`     | `AudienceResult`    |
| POST   | `/api/lenses/writers-room`   | `WritersRoomRequest`  | `WritersRoomResult` |
| POST   | `/api/lenses/cliffhanger`    | `CliffhangerRequest`  | `CliffhangerResult` |

Lens errors are returned as HTTP 500 with `detail=str(e)`. Request/response
schemas are defined in `app/schemas.py`.

## Project layout

```
backend/
  app/
    config.py        # settings + repo paths (REPO_ROOT, SKILLS_DIR, DATA_DIR)
    schemas.py       # Pydantic models shared across the API
    main.py          # FastAPI app + routes + CORS
    llm/             # Vertex clients (gemini_vertex, claude_vertex) + factory
    personas/        # persona loader + audience fan-out
    engine/          # cache, batch runner, aggregation
    lenses/          # audience, writers_room, cliffhanger
    db/              # firestore persistence (graceful)
```

Personas are authored as YAML under the monorepo `skills/` directory and sample
stories under `data/` (both resolved via `app/config.py`).
