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
    # Vertex location for all Gemini *chat* generation. The gemini-3.x IDs this
    # project is entitled to (e.g. gemini-3.5-flash) are served ONLY from the
    # "global" endpoint here — us-central1 exposes just the 2.5 family and 404s
    # on every 3.x call. So keep this "global". (Text embeddings work in both,
    # and TTS keeps its own ``tts_location`` below.)
    vertex_location: str = "global"

    # --- LLM provider --------------------------------------------------------
    # "gemini" (default, native to any GCP project) or "claude" (requires the
    # Claude models to be enabled in Vertex AI Model Garden).
    llm_provider: str = "gemini"
    # Single Gemini model across every chat tier: gemini-3.5-flash, served from
    # the "global" ``vertex_location`` above (verified reachable for this
    # project). Fast enough for the high-volume audience fan-out and strong
    # enough for the quality lenses, so we run one model everywhere for
    # consistency. If you change this, confirm the ID resolves on "global" first
    # (a wrong ID 404s on every call and silently drops agents).
    gemini_model: str = "gemini-3.5-flash"
    # Claude on Vertex: current-gen models use the bare ID; region-gated and
    # must be enabled in Vertex AI Model Garden before use.
    claude_model: str = "claude-sonnet-5"
    claude_location: str = "us-east5"

    # --- Per-lens model (Gemini) ---------------------------------------------
    # One model for every lens — gemini-3.5-flash on "global". Only used when
    # llm_provider == 'gemini'. Kept as separate fields so a single tier can be
    # overridden via env without disturbing the rest.
    model_audience: str = "gemini-3.5-flash"
    model_experts: str = "gemini-3.5-flash"
    model_rewrite: str = "gemini-3.5-flash"
    # Audience Simulator ("Living Audience") reaction agents. Statefulness comes
    # from persisted identity + memory, not from a heavier model, so the same
    # fast gemini-3.5-flash powers the 1000-agent panels too.
    model_sim: str = "gemini-3.5-flash"

    # --- Generation ----------------------------------------------------------
    temperature: float = 0.9        # variety across personas
    # Gemini spends output tokens on "thinking" — keep this generous so the
    # thinking budget never starves the structured JSON output.
    max_output_tokens: int = 8192
    concurrency: int = 10           # simultaneous LLM calls in the batch runner

    # --- Narration TTS ("hear the difference") -------------------------------
    # Voices the two Cliffhanger endings so the hook-score lift is *audible*: the
    # weak original read flat, the optimized cliffhanger read with dramatic,
    # in-character tension. Chirp 3 HD (Cloud TTS, GA) is the reliable engine;
    # Gemini 2.5 native TTS (preview) is tried first for richer delivery when
    # ``tts_engine`` allows and it proves reachable, else we fall back to Chirp.
    # Voice names are the shared Gemini/Chirp set (bare, e.g. "Charon"); the
    # Chirp voice id is derived as "<lang>-Chirp3-HD-<voice>".
    tts_engine: str = "auto"           # "auto" (Gemini→Chirp) | "chirp" | "gemini"
    tts_model: str = "gemini-2.5-flash-preview-tts"
    tts_location: str = "us-central1"  # preview-TTS region may differ; override if 404
    tts_language_code: str = "hi-IN"   # Hindi/Hinglish stories; Gemini auto-detects, Chirp uses this
    tts_voice_flat: str = "Vindemiatrix"  # soft, even girl voice — the passive original read
    tts_voice_dramatic: str = "Achernar"  # soft girl voice — the dramatic optimized read
    tts_rate_flat: float = 0.98
    tts_rate_dramatic: float = 1.06
    tts_max_chars: int = 1200          # cap synth input (payload + latency guard)

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
    # Optional explicit "open the graph in a browser" URL for the DB / Memory
    # tab's demo link. When unset it is derived from ``neo4j_uri`` (see
    # ``graph_browser_url``). Point it at your Aura console / instance if you
    # want the arrow to deep-link somewhere specific.
    neo4j_browser_url: str = ""
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

    # --- Audience Simulator ("Living Audience") ------------------------------
    # Genuine, stateful reaction agents that SEE a posted image + read the text
    # and react like real listeners. Budget is not the constraint here — these
    # run wider and deeper than the base audience lens.
    sim_panel_default: int = 200    # distinct persona-agents per run by default
    sim_panel_max: int = 1000       # hard cap on a single expensive fan-out
    sim_concurrency: int = 32       # simultaneous reaction agents in flight
    sim_synthesis_concurrency: int = 6  # bounded persona-generation batches
    sim_max_retries: int = 3        # retries on 429/503, with backoff + jitter
    sim_agentic: bool = True        # run the multi-step perceive→recall→react loop
    # How many large agent runs may be in flight at once (the run gate). Raised
    # above 1 so concurrent demos / judges don't block one another.
    max_concurrent_runs: int = 4
    planner_panel_default: int = 1000
    planner_scout_default: int = 100
    planner_finalists_default: int = 3
    # Pace the high-volume paired-comparison calls below the shared Vertex
    # request quota. Concurrency still hides individual response latency, while
    # start-rate pacing prevents a fast 1,000-agent burst from dropping agents.
    planner_requests_per_second: float = 5.0
    planner_max_retries: int = 6

    # --- RL / MDP (policy search over story decisions) -----------------------
    mdp_discount: float = 0.85
    mdp_lookahead: int = 2

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

    @property
    def graph_browser_url(self) -> str:
        """A best-effort URL to open the Neo4j graph in a browser, for demos.

        An explicit ``neo4j_browser_url`` wins. Otherwise derive it from the
        connection URI so the "Open in Neo4j" link just works:

        * local instance            -> the bundled Browser on :7474
        * self-hosted plain ``bolt://HOST`` -> that server's own Browser at
          ``http://HOST:7474`` (a TLS-hosted Browser can't talk to an
          unencrypted bolt endpoint, so this is the reliable target)
        * Aura / TLS (``+s`` schemes or ``*.databases.neo4j.io``) -> the hosted
          Neo4j Browser pre-targeted at this instance

        The user still authenticates in Neo4j itself — no credentials are ever
        put in the link. Empty when the graph isn't configured.
        """
        if self.neo4j_browser_url:
            return self.neo4j_browser_url
        uri = self.neo4j_uri.strip()
        if not uri:
            return ""
        from urllib.parse import quote

        scheme = uri.split("://", 1)[0].lower() if "://" in uri else ""
        host = uri.split("://", 1)[-1]          # drop scheme
        host = host.split("/", 1)[0]            # drop any path
        host = host.rsplit("@", 1)[-1]          # drop any embedded credentials
        hostname = host.split(":", 1)[0]        # drop any port
        if hostname in ("localhost", "127.0.0.1", "0.0.0.0", ""):
            return "http://localhost:7474"
        secure = scheme.endswith(("+s", "+ssc")) or hostname.endswith(".databases.neo4j.io")
        if secure:
            return f"https://browser.neo4j.io/?connectURL={quote(uri, safe='')}"
        return f"http://{hostname}:7474"

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
                "sim": self.model_sim,
            }.get(tier, self.gemini_model)
        return self.claude_model


settings = Settings()
