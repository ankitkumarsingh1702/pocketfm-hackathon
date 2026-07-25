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
    # Claude on Vertex: current-gen models use the bare ID; region-gated and
    # must be enabled in Vertex AI Model Garden before use.
    claude_model: str = "claude-sonnet-5"
    claude_location: str = "us-east5"

    # --- Per-lens model tiering (Gemini) -------------------------------------
    # Fast model for the high-volume audience fan-out; a stronger model for the
    # low-volume, quality-critical lenses. Only used when llm_provider == 'gemini'.
    model_audience: str = "gemini-2.5-flash"
    model_experts: str = "gemini-2.5-pro"
    model_rewrite: str = "gemini-2.5-pro"

    # --- Generation ----------------------------------------------------------
    temperature: float = 0.9        # variety across personas
    # Gemini 2.5 spends output tokens on "thinking" — keep this generous so the
    # thinking budget never starves the structured JSON output.
    max_output_tokens: int = 8192
    concurrency: int = 10           # simultaneous LLM calls in the batch runner

    # --- Persistence ---------------------------------------------------------
    use_firestore: bool = True
    firestore_database: str = "(default)"
    firestore_collection: str = "simulations"
    cache_dir: str = ".cache"       # local LLM-response cache (instant re-runs)

    # --- Knowledge graph (Neo4j) ---------------------------------------------
    # The story "canon" graph — shared, persistent agent memory across runs.
    # Fully optional and best-effort: when the URI/password are unset the engine
    # runs exactly as before (empty canon). Point NEO4J_URI at a Neo4j Aura
    # instance (neo4j+s://...) or a self-hosted server; credentials come from
    # the environment / Secret Manager, never the repo.
    use_graph: bool = True
    neo4j_uri: str = ""
    neo4j_username: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"
    # Upper bound on the canon-memory text injected into a persona/expert prompt.
    canon_max_chars: int = 2000

    # --- DB activity feed (judge-facing proof of shared memory) --------------
    # Every graph read/write is recorded into a small in-process ring buffer so
    # the "DB / Memory" tab can show, live, that agents read shared memory and
    # write their verdicts back. Purely observational and best-effort — never
    # affects engine behaviour.
    use_activity_log: bool = True
    activity_log_max: int = 200

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

    @property
    def graph_configured(self) -> bool:
        """True when Neo4j connection details are present (URI + password)."""
        return bool(self.neo4j_uri and self.neo4j_password)

    def model_for(self, tier: str) -> str:
        """Resolve the model id for a lens ``tier`` ('audience'|'experts'|'rewrite').

        Gemini uses per-tier models (fast for volume, strong for quality);
        other providers fall back to their single configured model.
        """
        if self.llm_provider == "gemini":
            return {
                "audience": self.model_audience,
                "experts": self.model_experts,
                "rewrite": self.model_rewrite,
            }.get(tier, self.gemini_model)
        return self.claude_model


settings = Settings()
