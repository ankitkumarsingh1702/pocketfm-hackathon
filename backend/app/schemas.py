"""Shared data contract for the Simulated Studio engine.

Every module (LLM clients, engine, lenses, API, frontend) depends on these
shapes. Treat this file as the single source of truth — do not redefine these
models elsewhere.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Story input
# ---------------------------------------------------------------------------


class Story(BaseModel):
    title: str
    episode: str | None = None
    text: str
    # Optional posted image for multimodal reactions (Audience Simulator). The
    # image is base64-encoded bytes WITHOUT a ``data:`` URI prefix; ``image_mime``
    # is an IANA image type such as ``image/png``. Text-only stories leave both
    # None and behave exactly as before.
    image_base64: str | None = None
    image_mime: str | None = None


# ---------------------------------------------------------------------------
# Personas / agents (loaded from skills/*.yaml)
# ---------------------------------------------------------------------------

PersonaKind = Literal["audience", "expert"]


class Persona(BaseModel):
    id: str
    name: str
    kind: PersonaKind
    segment: str | None = None          # audience archetype label, e.g. "Metro Binge-Watcher"
    role: str | None = None             # expert role, e.g. "Director"
    age: int | None = None
    gender: str | None = None
    city: str | None = None
    genres: list[str] = Field(default_factory=list)
    traits: list[str] = Field(default_factory=list)
    temperature: float | None = None    # per-agent sampling override (None = provider default)
    system_prompt: str


# ---------------------------------------------------------------------------
# LLM structured outputs (one per persona, per story)
# ---------------------------------------------------------------------------

# Ordered stages of a single episode. A listener "survives" up to their
# drop_point; "finished" means they listened to the very end.
DropPoint = Literal["hook", "early", "middle", "climax", "cliffhanger", "finished"]
DROP_STAGES: list[str] = ["hook", "early", "middle", "climax", "cliffhanger", "finished"]


class PersonaReaction(BaseModel):
    """An audience persona's reaction to one episode."""

    will_continue: bool = Field(description="Would this listener start the next episode?")
    hook_score: int = Field(ge=0, le=100, description="How gripping, 0-100.")
    drop_point: DropPoint = Field(description="Where in THIS episode they disengaged, or 'finished'.")
    reason: str = Field(description="One sentence: why they continue or drop.")
    emotion: str = Field(description="Dominant emotion in one or two words.")


class ExpertNote(BaseModel):
    """An expert persona's craft critique of a story."""

    verdict: Literal["strong", "mixed", "weak"]
    score: int = Field(ge=0, le=100)
    strengths: list[str]
    issues: list[str]
    fix_suggestion: str


# ---------------------------------------------------------------------------
# Aggregated results (returned by lenses / API)
# ---------------------------------------------------------------------------


class SegmentStat(BaseModel):
    segment: str
    count: int
    binge_pct: float
    avg_hook: float


class AudienceResult(BaseModel):
    total: int
    binge_pct: float                    # % who will start the next episode
    avg_hook_score: float
    drop_off_curve: list[float]         # retention (0-1) at each DROP_STAGES position
    stages: list[str] = Field(default_factory=lambda: list(DROP_STAGES))
    segments: list[SegmentStat]
    top_churn_reasons: list[str]
    sample_reactions: list[dict]        # a few raw {persona, reaction} for the UI


class ExpertFeedback(BaseModel):
    persona: str
    role: str
    note: ExpertNote


class AudienceVerdict(BaseModel):
    """The audience's collective voice in the Writers Room: are they following?"""

    following_pct: float                 # % of listeners who stay with the story
    avg_engagement: float                # mean hook score, 0-100
    comprehension: str                   # plain-language read on whether they follow it
    confusion_points: list[str]          # where the audience got lost
    representative_quotes: list[str]     # a few raw listener reactions


class WritersRoomResult(BaseModel):
    panel: list[ExpertFeedback]
    audience: AudienceVerdict | None = None
    consensus: str


class CliffhangerResult(BaseModel):
    original: str
    rewrite: str
    before_score: float                 # avg hook_score before rewrite
    after_score: float                  # avg hook_score after rewrite
    lift: float                         # after - before
    rationale: str


# ---------------------------------------------------------------------------
# API request bodies
# ---------------------------------------------------------------------------


class SimulateRequest(BaseModel):
    story: Story
    n: int | None = None                # audience size override


class WritersRoomRequest(BaseModel):
    story: Story
    # Optional edited rosters from the UI (agent profiles). When omitted, the
    # server loads the default personas from skills/*.yaml.
    experts: list[Persona] | None = None
    audience: list[Persona] | None = None


class CliffhangerRequest(BaseModel):
    story: Story
    weak_excerpt: str                   # the soft ending to rewrite


# ---------------------------------------------------------------------------
# Knowledge graph — LLM extraction (Gemini-safe: str / Literal / int / list of
# models only; NO free dict/Any, which the Vertex response_schema rejects)
# ---------------------------------------------------------------------------

# Node kinds in the story-canon graph.
EntityType = Literal[
    "Character", "PlotThread", "Clue", "Episode", "Location", "Theme", "AudienceSegment"
]


class ExtractedEntity(BaseModel):
    """One entity (node) the LLM found in an episode."""

    key: str = Field(description="A short id the model uses to refer to this entity in relations, e.g. 'naina'.")
    type: EntityType
    name: str = Field(description="Canonical human-readable name, e.g. 'Naina'.")
    description: str = Field(default="", description="One concise sentence about this entity.")


class ExtractedRelation(BaseModel):
    """A directed edge between two extracted entities, referenced by their keys."""

    source_key: str
    target_key: str
    type: str = Field(description="UPPER_SNAKE_CASE relation, e.g. APPEARS_IN, LOCATED_AT, SUSPECTS.")
    detail: str = Field(default="", description="Short qualifier for this edge.")


class ExtractedFact(BaseModel):
    """An atomic, checkable claim — the raw material for contradiction search."""

    subject_key: str = Field(description="Key of the entity the fact is about.")
    predicate: str = Field(description="Snake_case attribute, e.g. 'building_floor_count', 'status'.")
    object: str = Field(description="The asserted value as text, e.g. '5', 'sealed since 1998'.")


class CanonExtraction(BaseModel):
    """Everything the LLM pulled out of one episode."""

    entities: list[ExtractedEntity] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)
    facts: list[ExtractedFact] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Knowledge graph — read models (returned by the API; free dicts allowed here)
# ---------------------------------------------------------------------------


class CanonNodeView(BaseModel):
    id: str                              # stable graph key, e.g. 'Character:naina'
    label: str                          # node type, e.g. 'Character'
    name: str
    props: dict[str, str] = Field(default_factory=dict)


class CanonEdgeView(BaseModel):
    source: str                          # source node id
    target: str                          # target node id
    type: str                            # relation type, e.g. 'APPEARS_IN'
    detail: str = ""                     # how/why the connection was made (edge prop)


class CanonGraph(BaseModel):
    nodes: list[CanonNodeView] = Field(default_factory=list)
    edges: list[CanonEdgeView] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)   # e.g. {'Character': 4, ...}


class IngestRequest(BaseModel):
    story: Story
    # Optional per-session tag written onto every node/fact this ingest creates,
    # so the UI can scope the graph to "your story" (what THIS browser session
    # added) and reset only that — never the seeded demo canon.
    batch: str | None = None


class IngestResult(BaseModel):
    episode_id: str
    nodes_added: int
    edges_added: int
    facts_added: int = 0                                   # atomic facts written this ingest
    batch: str = ""                                        # session tag applied (if any)
    entities: list[str] = Field(default_factory=list)     # names ingested, for the UI
    # The full structured extraction, so the composer can show exactly what the
    # agents pulled out of the script and wrote to shared memory.
    extraction: CanonExtraction | None = None


class CanonPreviewResult(BaseModel):
    """Extract-only result for the live 'as you type' preview (nothing written)."""

    extraction: CanonExtraction = Field(default_factory=CanonExtraction)
    entity_count: int = 0
    relation_count: int = 0
    fact_count: int = 0


class CanonResetRequest(BaseModel):
    batch: str                                             # required — never wipe everything


class CanonResetResult(BaseModel):
    deleted: int = 0
    batch: str = ""


class ActivityEvent(BaseModel):
    """One recorded read/write against the canon graph (for the DB / Memory tab)."""

    seq: int                             # monotonic sequence number
    ts: float                            # unix timestamp
    op: Literal["read", "write", "skipped"]
    fn: str                              # store function that ran
    source: str                          # agent/lens that triggered it
    detail: str                          # human-readable sentence
    counts: dict[str, float] = Field(default_factory=dict)  # nodes/edges/segments…


class ActivityFeed(BaseModel):
    events: list[ActivityEvent] = Field(default_factory=list)
    # True totals across ALL persisted events (not just the returned page), so
    # the DB / Memory tiles reflect the full durable history.
    reads: int = 0
    writes: int = 0
    total: int = 0


# ---------------------------------------------------------------------------
# Planning — Tree & Graph Search (plot-hole detection + cliffhanger beam search)
# ---------------------------------------------------------------------------


class PlotHole(BaseModel):
    """A continuity/consistency issue found across the canon + this episode."""

    severity: Literal["high", "medium", "low"]
    location: str = Field(description="Where it occurs, e.g. a scene or line.")
    kind: str = Field(description="Short category, e.g. 'timeline', 'fact conflict', 'tone'.")
    description: str
    evidence: list[str] = Field(default_factory=list)     # supporting canon facts / quotes
    fix: str = Field(description="A concrete suggested fix.")
    episodes: list[str] = Field(default_factory=list)     # episodes this issue spans, e.g. ["Ep 4","Ep 41"]


class PlotHoleResult(BaseModel):
    holes: list[PlotHole] = Field(default_factory=list)
    canon_used: bool = False                              # were graph facts available?
    episodes_scanned: int = 0                             # episodes present in the canon
    facts_scanned: int = 0                                # total canon facts cross-checked
    pages_estimate: int = 0                               # ≈ script pages the canon represents


class PlanCandidate(BaseModel):
    """One node in the cliffhanger search tree."""

    id: str
    text: str
    hook_score: float
    delta: float                                          # hook_score - baseline
    parent_id: str | None = None
    depth: int = 0


class SearchTree(BaseModel):
    candidates: list[PlanCandidate] = Field(default_factory=list)
    best_id: str = ""
    rounds: int = 0
    baseline_score: float = 0.0
    audience_source: str = "default"                      # "living" (persisted KG audience) | "default"
    panel_size: int = 0                                   # listeners used as the scoring model


class PlotHolesRequest(BaseModel):
    story: Story


class PlanRequest(BaseModel):
    story: Story
    weak_excerpt: str
    beam_width: int | None = None
    depth: int | None = None


# ---------------------------------------------------------------------------
# Actions — State Graph (agentic showrunner loop)
# ---------------------------------------------------------------------------


class ShowrunnerResult(BaseModel):
    transcript: list[dict] = Field(default_factory=list)   # node-by-node log
    before_score: float = 0.0
    after_score: float = 0.0
    lift: float = 0.0
    contradictions_found: int = 0
    contradictions_fixed: int = 0
    converged: bool = True
    iterations: int = 0
    final_text: str = ""
    audience_source: str = "default"                      # "living" (persisted KG audience) | "default"


class ShowrunnerRequest(BaseModel):
    story: Story
    weak_excerpt: str | None = None


# ---------------------------------------------------------------------------
# RL — Markov Decision Process (policy search over story decisions)
# ---------------------------------------------------------------------------


class MdpStep(BaseModel):
    iteration: int
    chosen_action_id: str
    reward: float
    best_reward: float
    q_values: list[float] = Field(default_factory=list)   # one-step Q estimate per candidate action
    state: str = ""                                        # human-readable state at this step
    value: float = 0.0                                     # Q(s,a*) = reward + γ·V(s') for the chosen action


class MdpResult(BaseModel):
    steps: list[MdpStep] = Field(default_factory=list)
    baseline_reward: float = 0.0
    final_reward: float = 0.0
    best_action_text: str = ""
    policy: str = "greedy"
    discount: float = 0.0                                  # γ used in the Bellman look-ahead
    discounted_return: float = 0.0                         # Σ γ^t · reward_t along the chosen trajectory
    audience_source: str = "default"                      # "living" (persisted KG audience) | "default"


class MdpRequest(BaseModel):
    story: Story
    weak_excerpt: str
    iterations: int | None = None
    candidates_per_iter: int | None = None


# ---------------------------------------------------------------------------
# Audience Simulator ("Living Audience") — thousands of stateful, multimodal
# listener-agents that see a posted image + text and react like real listeners,
# persisted in the knowledge graph so they remember past posts.
# ---------------------------------------------------------------------------

# The single strongest engagement action a listener takes on a post.
SimEngagement = Literal[
    "scroll_past", "like", "comment", "share", "save", "subscribe", "binge"
]
SIM_ENGAGEMENTS: list[str] = [
    "scroll_past", "like", "comment", "share", "save", "subscribe", "binge"
]
# How positively the listener feels about the post.
SimSentiment = Literal["love", "like", "neutral", "mixed", "dislike"]
SIM_SENTIMENTS: list[str] = ["love", "like", "neutral", "mixed", "dislike"]


class SocialReaction(BaseModel):
    """One audience-agent's reaction to a posted episode/teaser (+image).

    Gemini-safe (str / Literal / int / bool only) so it works as a native
    Vertex ``response_schema``. ``reasoning`` and ``memory_note`` are the
    glass-box explainers: the agent's private 'why' and what past context (from
    its knowledge-graph memory) shaped this reaction.
    """

    will_listen: bool = Field(description="Would this listener actually hit play / start the episode?")
    hook_score: int = Field(ge=0, le=100, description="How gripping/appealing the post is, 0-100.")
    sentiment: SimSentiment = Field(description="Overall feeling about the post.")
    engagement: SimEngagement = Field(description="The single strongest action they take.")
    emotion: str = Field(description="Dominant emotion in one or two words.")
    comment: str = Field(description="The public comment they'd leave, in their own voice (1-2 sentences).")
    reasoning: str = Field(description="Private glass-box rationale: WHY they reacted this way.")
    memory_note: str = Field(default="", description="What prior context/history influenced them, if any.")


class AudienceReactionView(BaseModel):
    """A single agent's reaction joined with who reacted (for the UI feed)."""

    persona_id: str
    name: str
    segment: str | None = None
    age: int | None = None
    city: str | None = None
    will_listen: bool
    hook_score: int
    sentiment: str
    engagement: str
    emotion: str
    comment: str
    reasoning: str
    memory_note: str = ""


class SentimentStat(BaseModel):
    sentiment: str
    count: int
    pct: float


class EngagementStat(BaseModel):
    action: str
    count: int
    pct: float


class SimSegmentStat(BaseModel):
    segment: str
    count: int
    avg_hook: float
    positive_pct: float          # % love/like within the segment
    listen_pct: float            # % who would hit play


class AudienceSimResult(BaseModel):
    total: int                                   # agents who successfully reacted
    listen_pct: float                            # % who would hit play
    avg_hook_score: float
    virality: float                              # 0-100 composite of share/subscribe/comment intent
    sentiment_breakdown: list[SentimentStat] = Field(default_factory=list)
    engagement_funnel: list[EngagementStat] = Field(default_factory=list)
    segments: list[SimSegmentStat] = Field(default_factory=list)
    top_comments: list[AudienceReactionView] = Field(default_factory=list)
    reactions: list[AudienceReactionView] = Field(default_factory=list)   # sampled, capped for the UI
    dropped: int = 0                             # agents whose LLM call failed (surfaced, not hidden)


# --- LLM persona synthesis (Gemini-safe response_schema) -------------------


class SynthPersona(BaseModel):
    """One generated audience member. No id/kind/temperature — the generator
    assigns those; the model only invents the human."""

    name: str
    segment: str = Field(description="Audience archetype label, e.g. 'Metro Binge-Watcher'.")
    age: int = Field(ge=13, le=90)
    gender: str
    city: str
    genres: list[str] = Field(default_factory=list)
    traits: list[str] = Field(default_factory=list)
    system_prompt: str = Field(description="First-person listener persona: taste, habits, what earns their next tap.")


class SynthBatch(BaseModel):
    personas: list[SynthPersona] = Field(default_factory=list)


# --- API request / response bodies -----------------------------------------


class GeneratePersonasRequest(BaseModel):
    n: int | None = None                         # how many distinct members to generate
    brief: str | None = None                     # optional targeting brief, e.g. "urban Gen-Z thriller fans"
    seed_segments: list[str] | None = None       # archetype hints to diversify around
    persist: bool = True                         # write generated members to the knowledge graph


class AudienceLibrary(BaseModel):
    members: list[Persona] = Field(default_factory=list)
    total: int = 0
    source: str = "graph"                        # "graph" | "generated" | "defaults"


class AudienceSimRequest(BaseModel):
    story: Story                                 # the post being tested (title/text/optional image)
    # Edited roster from the UI (agent profiles). When omitted, the server pulls
    # the persisted audience from the knowledge graph, else the default panel.
    audience: list[Persona] | None = None
    n: int | None = None                         # panel size when sampling/generating
    use_library: bool = True                     # prefer the persisted KG audience when available
