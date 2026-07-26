"""
Mood-First Search — configuration + cold-start logic.

Tuning lives here so nobody edits schemas.py to change a number.
"""

from __future__ import annotations

import re
from typing import Optional

from app.mood.schemas import (
    ClarifyingQuestion,
    ClarifyOption,
    Destination,
    MoodAxes,
    MoodQuery,
    MoodStarter,
    SPARSITY_THRESHOLD,
)

# Crisis support lines surfaced by the safety path. Kept here rather than in
# any API module so both the real service and any test harness reach the same
# numbers — a stale helpline is a worse bug than a stale mood axis.
SUPPORT_RESOURCES: list[str] = [
    "Tele-MANAS: 14416",
    "KIRAN: 1800-599-0019",
]


# --------------------------------------------------------------------------
# Empty state — we show QUERIES, not shows
# --------------------------------------------------------------------------
# Purpose is teaching, not browsing. In one glance the listener learns that the
# box takes a feeling. Cover the destination space so no matter who opens the
# app, one of these is close to true. Keep it to 8 — this is a doorway, not a menu.

MOOD_STARTERS: list[MoodStarter] = [
    MoodStarter(
        id="rain_alone",
        text="Baarish ho rahi hai aur kisi se baat nahi karni",
        hint_destination="sit_with",
    ),
    MoodStarter(
        id="post_breakup",
        text="Something that feels like a rainy Sunday after heartbreak",
        hint_destination=None,  # deliberately ambiguous — this is the hero query
    ),
    MoodStarter(
        id="long_drive",
        text="Long drive hai, jagaye rakhna hai",
        hint_destination="escape",
    ),
    MoodStarter(
        id="sleep",
        text="Kuch aisa jo sona aasan kar de",
        hint_destination="sleep",
    ),
    MoodStarter(
        id="afterglow",
        text="Abhi ek series khatam ki, us jaisa feel chahiye",
        hint_destination=None,
    ),
    MoodStarter(
        id="company",
        text="Akela hoon, bas koi awaaz chahiye jo saath lage",
        hint_destination="company",
    ),
    MoodStarter(
        id="too_much",
        text="Din bohot heavy tha, kuch halka chahiye",
        hint_destination="lift_gently",
    ),
    MoodStarter(
        id="make_sense",
        text="Kuch samajh nahi aa raha, kuch aisa jo cheezein clear kare",
        hint_destination="make_sense_of",
    ),
]


# --------------------------------------------------------------------------
# Sliders — refinement in mood space
# --------------------------------------------------------------------------
# Slider value is -1.0..1.0. Multiply by these to get axis deltas.
# One slider touches several axes on purpose: "heavier" is not one number,
# it is weight up AND catharsis up AND pace down.

SLIDER_AXIS_MAP: dict[str, dict[str, float]] = {
    "heavier": {"weight": 0.30, "catharsis": 0.20, "valence": -0.20, "pace": -0.10},
    "faster": {"pace": 0.35, "arousal": 0.25, "tension": 0.10},
    "warmer": {"warmth": 0.35, "companionship": 0.25, "hope": 0.15, "tension": -0.10},
    "stranger": {"tension": 0.20, "arousal": 0.15, "warmth": -0.20, "companionship": -0.15},
}

# The two ends of each control, as the listener sees them. These render directly
# beneath a shelf heading, so they follow the same rule: the interface speaks
# plain English even though it reads Hinglish.
SLIDER_LABELS: dict[str, tuple[str, str]] = {
    "heavier": ("Lighter", "Heavier"),
    "faster": ("Slower", "Faster"),
    "warmer": ("More distant", "More intimate"),
    "stranger": ("More familiar", "Stranger"),
}


def slider_deltas_to_axis_deltas(slider_deltas: dict[str, float]) -> dict[str, float]:
    """Fold slider positions into a single set of axis deltas."""
    out: dict[str, float] = {}
    for slider, value in slider_deltas.items():
        mapping = SLIDER_AXIS_MAP.get(slider)
        if mapping is None:
            raise ValueError(f"unknown slider: {slider}")
        value = max(-1.0, min(1.0, value))
        for axis, weight in mapping.items():
            out[axis] = out.get(axis, 0.0) + weight * value
    return out


# --------------------------------------------------------------------------
# Destinations -> mood space
# --------------------------------------------------------------------------

DESTINATION_TARGETS: dict[str, MoodAxes] = {
    "sit_with": MoodAxes(
        valence=-0.55, arousal=0.25, tension=0.25, warmth=0.65, pace=0.25,
        catharsis=0.88, hope=0.40, companionship=0.45, weight=0.80,
    ),
    "lift_gently": MoodAxes(
        valence=0.35, arousal=0.35, tension=0.20, warmth=0.80, pace=0.35,
        catharsis=0.35, hope=0.78, companionship=0.55, weight=0.30,
    ),
    "company": MoodAxes(
        valence=0.15, arousal=0.30, tension=0.15, warmth=0.90, pace=0.30,
        catharsis=0.30, hope=0.60, companionship=0.92, weight=0.25,
    ),
    "escape": MoodAxes(
        valence=0.20, arousal=0.70, tension=0.60, warmth=0.40, pace=0.80,
        catharsis=0.25, hope=0.55, companionship=0.25, weight=0.45,
    ),
    "make_sense_of": MoodAxes(
        valence=0.05, arousal=0.40, tension=0.35, warmth=0.55, pace=0.40,
        catharsis=0.55, hope=0.60, companionship=0.60, weight=0.60,
    ),
    "sleep": MoodAxes(
        valence=0.20, arousal=0.08, tension=0.05, warmth=0.85, pace=0.12,
        catharsis=0.15, hope=0.60, companionship=0.70, weight=0.20,
    ),
}

# Hard retrieval bounds. Applied as structured filters BEFORE vector search, so
# an emotionally wrong item can never make it to the reranker at all.
DESTINATION_FILTERS: dict[str, dict[str, tuple[float, float]]] = {
    "sit_with": {"catharsis": (0.55, 1.0), "arousal": (0.0, 0.50), "tension": (0.0, 0.55)},
    "lift_gently": {"hope": (0.55, 1.0), "weight": (0.0, 0.55), "tension": (0.0, 0.45)},
    "company": {"companionship": (0.60, 1.0), "warmth": (0.60, 1.0), "tension": (0.0, 0.40)},
    "escape": {"pace": (0.55, 1.0), "companionship": (0.0, 0.55)},
    "make_sense_of": {"catharsis": (0.35, 1.0), "hope": (0.40, 1.0)},
    "sleep": {"arousal": (0.0, 0.25), "pace": (0.0, 0.30), "tension": (0.0, 0.25)},
}

# --------------------------------------------------------------------------
# Destination target + the listener's own calibration
# --------------------------------------------------------------------------
# DESTINATION_TARGETS is the centroid of an intent. It is not the whole answer:
# two listeners can both want `sit_with` and need materially different things
# from it. `intensity` and `intensity_tolerance` are parsed on every query and
# were, until this function existed, read by nothing in the retrieval path --
# the target was the same point for everyone.
#
# The split that makes them interpretable:
#   intensity_tolerance -> how heavy we are WILLING to go
#   intensity           -> how much HOLDING they need right now
#
# Both are deliberately asymmetric. Low tolerance pulls heaviness down, but a
# raw listener never gets *more* dread added, and heaviness is never pushed up
# by rawness alone -- the failure mode we care about is making it worse, so the
# modulation can soften but only cautiously intensify.

TARGET_GAIN: dict[str, float] = {
    "weight": 0.30,        # tolerance: how heavy we will go
    "catharsis": 0.20,     # tolerance: how much tear-release we will aim at
    "warmth": 0.20,        # rawness: be held more
    "companionship": 0.15, # rawness: be spoken to more
    "tension": 0.10,       # rawness: less dread, never more
}


def resolve_target(query: MoodQuery, destination: Destination) -> MoodAxes:
    """The destination centroid, calibrated to this listener's state.

    Pure and side-effect free; `MoodAxes.nudge` clamps every axis, so no
    combination of inputs can produce an out-of-range target.
    """
    base = DESTINATION_TARGETS[destination]

    room = query.intensity_tolerance - 0.5   # -0.5..0.5  heaviness allowed
    raw = max(0.0, query.intensity - 0.5)    #   0..0.5   how raw, one-sided

    return base.nudge({
        "weight": room * TARGET_GAIN["weight"],
        "catharsis": room * TARGET_GAIN["catharsis"],
        "warmth": raw * TARGET_GAIN["warmth"],
        "companionship": raw * TARGET_GAIN["companionship"],
        "tension": -raw * TARGET_GAIN["tension"],
    })


# How much longer than the stated session an arc may run before we exclude it.
# Generous on purpose: "ek ghanta" is an estimate, not a train timetable, and
# starving a shelf over a rounding error is the worse outcome.
SESSION_SLACK = 1.5


# Shelf headings and their one-line explanations.
#
# The heading names the LISTENER'S INTENT, not the mood of the content. "Sit in
# it" read as a fragment of someone else's sentence — you had to already know the
# concept to parse it. "Stay with the feeling" says what the listener is choosing
# to do, so the three headings become three answers to "what do you want from
# this?" and the shelves compare against each other on sight.
#
# The subtitle then says what the content will actually be like. Written as the
# product's own voice — plain, complete English sentences. Hinglish belongs in
# what a LISTENER types, not in the labels the interface writes back at them.
SHELF_COPY: dict[str, tuple[str, str]] = {
    "sit_with": (
        "Stay with the feeling",
        "Slow and unhurried. It sits with what you're feeling instead of trying to fix it.",
    ),
    "lift_gently": (
        "Lift it, gently",
        "Warm and quietly hopeful, without forcing cheerfulness on you.",
    ),
    "company": (
        "Somebody with you",
        "A close, conversational voice — for when the point is simply not being alone.",
    ),
    "escape": (
        "Somewhere else entirely",
        "Fast-moving and absorbing enough to hold your full attention.",
    ),
    "make_sense_of": (
        "Make sense of it",
        "Reflective and clear-eyed. Gives shape to something that is hard to name.",
    ),
    "sleep": (
        "Wind down towards sleep",
        "Quiet, slow and even. Written to be half-heard on the way under.",
    ),
}


# --------------------------------------------------------------------------
# Sparsity — when to ask instead of guessing
# --------------------------------------------------------------------------
# The LLM parser sets sparsity_score. This heuristic is the FLOOR: it runs
# first, costs nothing, and catches the obvious cases before we spend a token.
# Rule we agreed on: ask ONLY when three shelves could not answer it anyway.

_EMOTION_WORDS = {
    "sad", "happy", "lonely", "heartbreak", "breakup", "anxious", "angry", "numb",
    "tired", "empty", "scared", "hopeful", "nostalgic", "restless", "guilty",
    "udaas", "akela", "gussa", "sukoon", "dard", "khushi", "thaka", "pareshan",
    "dukhi", "bechain", "tanha",
}
_CONTEXT_WORDS = {
    "rain", "baarish", "night", "raat", "morning", "subah", "drive", "commute",
    "sleep", "sona", "neend", "work", "office", "home", "ghar", "sunday",
    "weekend", "travel", "gym", "walk", "monsoon", "winter", "sardi",
}


def heuristic_sparsity(text: str) -> float:
    """Cheap pre-LLM estimate. 0 = rich, 1 = almost no signal."""
    tokens = set(re.findall(r"[a-zA-Z\u0900-\u097F]+", text.lower()))
    if not tokens:
        return 1.0

    score = 1.0
    if tokens & _EMOTION_WORDS:
        score -= 0.45
    if tokens & _CONTEXT_WORDS:
        score -= 0.30
    if len(tokens) >= 6:
        score -= 0.15
    if len(tokens) >= 12:
        score -= 0.10
    return max(0.0, min(1.0, score))


# The one question. Note every option resolves straight into mood space, so the
# answer moves the target vector without a second LLM call.
DEFAULT_CLARIFY = ClarifyingQuestion(
    question="What would you like this to do for you?",
    options=[
        ClarifyOption(id="c_sit", label="Stay with how I'm feeling",
                      resolves_destination="sit_with"),
        ClarifyOption(id="c_company", label="Keep me company",
                      resolves_destination="company"),
        ClarifyOption(id="c_escape", label="Take me somewhere else",
                      resolves_destination="escape"),
        ClarifyOption(id="c_sleep", label="Help me fall asleep",
                      resolves_destination="sleep"),
    ],
    skip_label="Anything is fine",
)

# When we already know the destination but a constraint is missing, ask about
# the constraint instead. These change results far more than intent does.
SESSION_CLARIFY = ClarifyingQuestion(
    question="How long have you got?",
    options=[
        ClarifyOption(id="s_short", label="10 to 15 minutes",
                      axis_deltas={"pace": 0.15}),
        ClarifyOption(id="s_medium", label="About an hour",
                      axis_deltas={"weight": 0.05}),
        ClarifyOption(id="s_long", label="All night",
                      axis_deltas={"weight": 0.15, "pace": -0.10}),
    ],
    skip_label="Anything is fine",
)


def build_clarifying_question(query: MoodQuery) -> Optional[ClarifyingQuestion]:
    """Return at most ONE question, or None if we should just answer.

    Order matters:
      1. distress  -> never ask, hand off to the safety path
      2. explicit destination -> never ask about intent, they told us
      3. sparse    -> ask the intent question
      4. otherwise -> answer with three shelves
    """
    if query.distress_flag:
        return None
    if query.destination is not None:
        if query.session_length_min is None and query.sparsity_score >= SPARSITY_THRESHOLD:
            return SESSION_CLARIFY
        return None
    if query.sparsity_score >= SPARSITY_THRESHOLD:
        return DEFAULT_CLARIFY
    return None


def rank_destinations(query: MoodQuery) -> list[Destination]:
    """Pick the three shelves, in order.

    destination_prior only reorders and breaks ties. It never filters and never
    beats an explicit destination — otherwise last week's mood pollutes tonight.
    """
    if query.destination is not None:
        head = query.destination
    else:
        head = None

    ordered: list[Destination] = []
    if head:
        ordered.append(head)

    negative = any(
        w in " ".join(query.felt_state).lower()
        for w in ("heartbreak", "sad", "lonely", "grief", "breakup", "empty", "numb")
    )
    pool: list[Destination] = (
        ["sit_with", "company", "escape"] if negative
        else ["company", "lift_gently", "escape"]
    )

    if query.destination_prior and query.destination_prior in pool:
        pool.remove(query.destination_prior)
        pool.insert(0, query.destination_prior)

    for d in pool:
        if d not in ordered:
            ordered.append(d)
    return ordered[:3]
