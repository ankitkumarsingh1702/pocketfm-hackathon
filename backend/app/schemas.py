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
    city: str | None = None
    genres: list[str] = Field(default_factory=list)
    traits: list[str] = Field(default_factory=list)
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


class WritersRoomResult(BaseModel):
    panel: list[ExpertFeedback]
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


class CliffhangerRequest(BaseModel):
    story: Story
    weak_excerpt: str                   # the soft ending to rewrite
