"""
Mood-First Search — FROZEN CONTRACT (H0)

Nobody changes this file alone. If it must change, all three of us change it
together and everyone re-runs their mocks. Every other module imports from here.

Ownership after this file is frozen:
    Ankit  -> parser (MoodQuery), API surface, frontend
    Ritik  -> fingerprinter (MoodFingerprint)
    Sahil  -> retrieval + rerank (MoodAxes math, DESTINATION_*), eval
"""

from __future__ import annotations

import math
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------

Destination = Literal[
    "sit_with",       # let me feel it properly
    "lift_gently",    # nudge me upward, don't shout at me
    "company",        # don't fix me, just don't leave me alone
    "escape",         # take me somewhere else entirely
    "make_sense_of",  # help me understand what happened
    "sleep",          # carry me under
]

AXIS_NAMES = (
    "valence", "arousal", "tension", "warmth", "pace",
    "catharsis", "hope", "companionship", "weight",
)

# Retrieval weights. Tuned by Sahil against the persona panel — these are the
# starting guesses, not gospel. catharsis/warmth carry the most signal for the
# emotionally-loaded queries we actually care about.
AXIS_WEIGHTS: dict[str, float] = {
    "valence": 1.0, "arousal": 0.8, "tension": 0.9, "warmth": 1.2,
    "pace": 0.6, "catharsis": 1.3, "hope": 1.0, "companionship": 0.7,
    "weight": 0.9,
}


# --------------------------------------------------------------------------
# MoodAxes — the shared coordinate system
# --------------------------------------------------------------------------

class MoodAxes(BaseModel):
    """One point in mood space.

    Used three ways, and it is the same object every time:
      1. the affective signature of a piece of content  (Ritik)
      2. the target point a query resolves to           (Ankit)
      3. the thing a slider or a clarify-answer nudges  (Ankit -> Sahil)
    """

    valence: float = Field(0.0, ge=-1.0, le=1.0, description="bleak -> uplifting")
    arousal: float = Field(0.5, ge=0.0, le=1.0, description="still -> frantic")
    tension: float = Field(0.5, ge=0.0, le=1.0, description="safe -> dread")
    warmth: float = Field(0.5, ge=0.0, le=1.0, description="clinical -> held")
    pace: float = Field(0.5, ge=0.0, le=1.0, description="slow-burn -> propulsive")
    catharsis: float = Field(0.5, ge=0.0, le=1.0, description="numb -> tear-releasing")
    hope: float = Field(0.5, ge=0.0, le=1.0, description="hopeless -> redemptive")
    companionship: float = Field(0.5, ge=0.0, le=1.0, description="observing -> spoken to")
    weight: float = Field(0.5, ge=0.0, le=1.0, description="frothy -> heavy")

    def as_vector(self) -> list[float]:
        """valence is rescaled to 0..1 so every axis shares one range."""
        out = []
        for name in AXIS_NAMES:
            v = getattr(self, name)
            out.append((v + 1.0) / 2.0 if name == "valence" else v)
        return out

    def distance(self, other: "MoodAxes") -> float:
        """Weighted euclidean distance. Lower is closer."""
        a, b = self.as_vector(), other.as_vector()
        total = sum(
            AXIS_WEIGHTS[name] * (x - y) ** 2
            for name, x, y in zip(AXIS_NAMES, a, b)
        )
        return math.sqrt(total / sum(AXIS_WEIGHTS.values()))

    def nudge(self, deltas: dict[str, float]) -> "MoodAxes":
        """Apply signed deltas and clamp. Pure — returns a new object.

        This is the ONLY way the target point moves after parse. Sliders call
        it, clarify-answers call it. No LLM in this path, which is what keeps
        refinement under 200ms.
        """
        data = self.model_dump()
        for name, delta in deltas.items():
            if name not in AXIS_NAMES:
                raise ValueError(f"unknown axis: {name}")
            lo = -1.0 if name == "valence" else 0.0
            data[name] = max(lo, min(1.0, data[name] + delta))
        return MoodAxes(**data)


# --------------------------------------------------------------------------
# Content side — Ritik
# --------------------------------------------------------------------------

class MoodFingerprint(BaseModel):
    """The affective signature of ONE ARC. Never a whole series.

    Series-level mood is an average of incompatible things and it is useless.
    We index arcs and we return doorways.
    """

    content_id: str
    series_id: str
    series_title: str
    arc_label: str = Field(description="human-facing, e.g. 'the monsoon arc'")
    entry_episode: int = Field(ge=1, description="where we tell the listener to start")
    episode_span: tuple[int, int]

    axes: MoodAxes

    sensory_tags: list[str] = Field(
        default_factory=list,
        description="rain, night, small-room, monsoon, open-road, winter-quilt, crowd",
    )
    vibe_sentence: str = Field(
        description="one line, listener language, NO plot spoilers, no genre words"
    )
    good_for: list[str] = Field(default_factory=list)
    contraindicated_for: list[str] = Field(
        default_factory=list,
        description=(
            "Load-bearing. This is what stops 'rainy romance where lovers are "
            "torn apart' being served to someone in fresh heartbreak."
        ),
    )

    duration_min: int
    language: str = "en"
    audio_verified: bool = Field(
        False, description="True = went through ASR+prosody (Tier A). False = text-only (Tier B)."
    )
    axes_variance: float = Field(
        0.0, ge=0.0, description="spread across chunks; high = this arc has range"
    )
    confidence: float = Field(0.5, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_span(self) -> "MoodFingerprint":
        lo, hi = self.episode_span
        if lo > hi:
            raise ValueError("episode_span must be (low, high)")
        if not (lo <= self.entry_episode <= hi):
            raise ValueError("entry_episode must fall inside episode_span")
        return self


# --------------------------------------------------------------------------
# Query side — Ankit
# --------------------------------------------------------------------------

class Situation(BaseModel):
    time_of_day: Optional[str] = None
    weather: Optional[str] = None
    solitude: Optional[Literal["alone", "with_others", "unknown"]] = "unknown"
    activity: Optional[str] = None
    place: Optional[str] = None


class MoodQuery(BaseModel):
    """Output of the parser. The LLM fills this; nothing downstream re-parses."""

    raw_text: str

    situation: Situation = Field(default_factory=Situation)
    felt_state: list[str] = Field(default_factory=list)
    intensity: float = Field(0.5, ge=0.0, le=1.0)

    destination: Optional[Destination] = Field(
        None, description="None = ambiguous -> generate shelves"
    )
    intensity_tolerance: float = Field(0.5, ge=0.0, le=1.0)
    session_length_min: Optional[int] = None

    language: str = "en"
    avoid_tags: list[str] = Field(default_factory=list)

    # --- cold-start additions ------------------------------------------------
    sparsity_score: float = Field(
        0.0, ge=0.0, le=1.0,
        description=(
            "How under-specified this query is. 0 = rich emotional content, "
            "1 = almost no signal ('bore ho raha hoon'). Above "
            "SPARSITY_THRESHOLD we ask ONE question instead of guessing three "
            "hypotheses we cannot actually distinguish."
        ),
    )
    destination_prior: Optional[Destination] = Field(
        None,
        description=(
            "Supplied from MoodProfile, NOT parsed from text. Learned from which "
            "shelf this listener historically taps. Only reorders shelves and "
            "breaks ties — never filters, never overrides an explicit destination."
        ),
    )

    distress_flag: bool = False

    @property
    def needs_clarification(self) -> bool:
        # An explicit destination beats sparsity: if they told us what they want,
        # a thin query is fine.
        if self.distress_flag or self.destination is not None:
            return False
        return self.sparsity_score >= SPARSITY_THRESHOLD


SPARSITY_THRESHOLD = 0.60


# --------------------------------------------------------------------------
# Cold start
# --------------------------------------------------------------------------

class MoodStarter(BaseModel):
    """A pre-written query for the empty state.

    We show QUERIES, not shows. Showing shows is quietly reintroducing the
    browse grid this product exists to replace.
    """

    id: str
    text: str
    hint_destination: Optional[Destination] = None


class ClarifyOption(BaseModel):
    """One tappable answer.

    Each option resolves directly into mood space. That is the whole point —
    the answer moves the target vector with no second LLM call.
    """

    id: str
    label: str
    resolves_destination: Optional[Destination] = None
    axis_deltas: dict[str, float] = Field(default_factory=dict)


class ClarifyingQuestion(BaseModel):
    """Exactly one question. Never two. Never a form."""

    question: str
    options: list[ClarifyOption] = Field(min_length=2, max_length=4)
    skip_label: str = "Kuch bhi chalega"

    @model_validator(mode="after")
    def _options_do_something(self) -> "ClarifyingQuestion":
        for o in self.options:
            if o.resolves_destination is None and not o.axis_deltas:
                raise ValueError(f"option '{o.id}' resolves to nothing")
        return self


class MoodProfile(BaseModel):
    """Durable, per-listener. NOT a mood — a calibration.

    Mood is state; this is the lens we read their words through. Learned free
    from shelf taps: every 3-shelf result is a labelled datapoint.

    ROADMAP for the hackathon. Defined now so the contract does not move later.
    """

    user_id: str
    vocabulary: dict[str, str] = Field(default_factory=dict)
    scale_calibration: dict[str, float] = Field(default_factory=dict)
    hard_contraindications: list[str] = Field(default_factory=list)
    destination_prior: dict[str, float] = Field(
        default_factory=dict, description="destination -> tap share"
    )
    observations: int = 0

    def top_prior(self, min_observations: int = 5) -> Optional[Destination]:
        if self.observations < min_observations or not self.destination_prior:
            return None
        return max(self.destination_prior.items(), key=lambda kv: kv[1])[0]  # type: ignore[return-value]


# --------------------------------------------------------------------------
# Response — the shape the frontend switches on
# --------------------------------------------------------------------------

class ResultCard(BaseModel):
    content_id: str
    # ADDITIVE, post-freeze. The frontend needs to fetch episodes for a result
    # and content_id is an ARC id — deriving the series from it by string
    # surgery couples the client to an id format that was never promised.
    # Defaulted so nothing built against the original contract breaks.
    series_id: str = ""
    series_title: str
    arc_label: str
    entry_episode: int
    entry_label: str = Field(description="e.g. 'Start at Ep 34 — the monsoon arc'")
    explanation: str = Field(
        description="One line. Emotional register, not metadata-speak. This is the line people quote."
    )
    vibe_sentence: str
    duration_min: int
    audio_verified: bool
    score: float = Field(ge=0.0, le=1.0)


class Shelf(BaseModel):
    id: str
    label: str = Field(description="human, e.g. 'Sit in it'")
    subtitle: str
    destination: Destination
    target_axes: MoodAxes = Field(description="frontend sends this back on refine")
    results: list[ResultCard]


class SearchResponse(BaseModel):
    """mode is the discriminator. Frontend renders one of three screens."""

    query_id: str
    mode: Literal["shelves", "clarify", "safety"]
    parsed: MoodQuery

    shelves: list[Shelf] = Field(default_factory=list)
    clarifying_question: Optional[ClarifyingQuestion] = None
    safety_message: Optional[str] = None
    support_resources: list[str] = Field(default_factory=list)

    latency_ms: int = 0

    @model_validator(mode="after")
    def _mode_matches_payload(self) -> "SearchResponse":
        if self.mode == "shelves" and not self.shelves:
            raise ValueError("mode='shelves' needs shelves")
        if self.mode == "clarify" and self.clarifying_question is None:
            raise ValueError("mode='clarify' needs a clarifying_question")
        if self.mode == "safety" and not self.safety_message:
            raise ValueError("mode='safety' needs a safety_message")
        return self


class RefineRequest(BaseModel):
    """Slider drag. No LLM touches this path."""

    query_id: str
    shelf_id: str
    current_axes: MoodAxes
    slider_deltas: dict[str, float] = Field(
        description="slider name -> -1.0..1.0, mapped via SLIDER_AXIS_MAP"
    )


class ClarifyAnswerRequest(BaseModel):
    query_id: str
    option_id: Optional[str] = Field(None, description="None = user skipped")
