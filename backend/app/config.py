"""Application settings and repo paths.

All GCP access uses Application Default Credentials (ADC) — run
`gcloud auth application-default login` once. No keys live in this repo.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Repo paths (skills/ and data/ live at the monorepo root, next to backend/)
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent  # .../backend
REPO_ROOT = BACKEND_DIR.parent                         # monorepo root
SKILLS_DIR = REPO_ROOT / "skills"
DATA_DIR = REPO_ROOT / "data"


class Settings(BaseSettings):
    """Runtime configuration. Override any field via environment or backend/.env."""

    # --- GCP / Vertex AI -----------------------------------------------------
    google_cloud_project: str = "pocketfm-hackathon"
    # Gemini-on-Vertex works in most regions incl. us-central1 and "global".
    vertex_location: str = "us-central1"

    # --- LLM provider --------------------------------------------------------
    # "gemini" (default, native to any GCP project) or "claude" (requires the
    # Claude models to be enabled in Vertex AI Model Garden).
    llm_provider: str = "gemini"
    gemini_model: str = "gemini-2.5-flash"
    # Claude on Vertex uses the '@'-dated ID form and is region-gated.
    claude_model: str = "claude-haiku-4-5@20251001"
    claude_location: str = "us-east5"

    # --- Generation ----------------------------------------------------------
    temperature: float = 0.9        # variety across personas
    max_output_tokens: int = 1024
    concurrency: int = 10           # simultaneous LLM calls in the batch runner

    # --- Persistence ---------------------------------------------------------
    use_firestore: bool = True
    firestore_database: str = "(default)"
    firestore_collection: str = "simulations"
    cache_dir: str = ".cache"       # local LLM-response cache (instant re-runs)

    # --- Simulation ----------------------------------------------------------
    # Number of audience listeners to fan out to for a "representative 1000".
    # Keep modest for fast/cheap live demos; present as a panel of 1000.
    audience_fanout: int = 60

    # --- API -----------------------------------------------------------------
    cors_origins: str = "http://localhost:5173,http://localhost:4173"

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
