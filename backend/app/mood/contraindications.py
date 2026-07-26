"""
Mood-First Search — contraindication matching.

This module is the trap-avoidance mechanism. It is what stops "rainy-season
romance where the lovers are torn apart" being served to someone in fresh
heartbreak, despite that item having near-perfect lexical and semantic overlap
with the query. Everything else in retrieval optimises for similarity; this is
the only part that optimises for *not making it worse*.

DESIGN NOTE -- why a closed vocabulary
--------------------------------------
`MoodFingerprint.contraindicated_for` is free text ("someone who wants
cheering up"). Free text is right for the fingerprinter -- an LLM writes it
well and it reads well to a human. Free text is WRONG for matching: embedding
similarity between "someone who wants cheering up" and a listener's parsed
state is mushy exactly where we need it sharp, and a false negative here is
the single most harmful failure the product can produce.

So: keep the field open, close the vocabulary at index time. Free text is
mapped to codes deterministically, once, during indexing. Matching is then set
intersection -- exact, instant, debuggable, and testable.

The contract in schemas.py is NOT modified. Derivation lives here.
"""

from __future__ import annotations

import re
from typing import Iterable

from app.mood.schemas import MoodQuery

# Closed vocabulary of listener states a piece of content can be wrong for.
CODES = (
    "fresh_grief",      # recent death/loss, raw
    "breakup",          # romantic rupture
    "wants_cheering",   # explicitly wants to be lifted, not sat with
    "active_anxiety",   # keyed up, panicky
    "loneliness",       # alone and feeling it
    "sleep_seeking",    # trying to go under
    "low_attention",    # driving, commuting, working
)

# Free text -> code. Ordered; a phrase can map to several codes.
_TEXT_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    (r"\b(grief|grieving|bereave|mourn|death of|dying|loss of a|funeral)\b", ("fresh_grief",)),
    (r"\b(breakup|break-up|heartbreak|broken heart|divorce|separation)\b", ("breakup",)),
    (r"\b(cheer(ed|ing)? up|wants? to feel better|lift(ed|ing)?|uplift|needs? hope)\b", ("wants_cheering",)),
    (r"\b(anxiet|anxious|panic|on edge|keyed up|stress)\b", ("active_anxiety",)),
    (r"\b(lonely|loneliness|alone|isolated)\b", ("loneliness",)),
    (r"\b(sleep|sleeping|falling asleep|bedtime|insomnia|winding down)\b", ("sleep_seeking",)),
    (r"\b(driv|commut|working|focus|concentrat)\w*\b", ("low_attention",)),
]

# Listener-side: what the parsed query tells us about their state.
#
# Split into EVENT and MOOD evidence, because the intensity gate below must
# treat them differently:
#
#   _EVENT_PATTERNS  name a thing that HAPPENED ("she died", "just got dumped").
#                    The event is the evidence. Intensity cannot argue with it.
#   _FELT_PATTERNS   name a feeling ("sad", "udaas"). Real, but a mild version
#                    of the feeling is not a contraindication, so these stay
#                    subject to the intensity gate.
#
# Hinglish is first-class here, not an afterthought: the listeners who type
# "chhod diya" are the same ones this layer exists to protect.
_EVENT_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    (r"\b(died|passed away|funeral|guzar ga(?:ya|yi)|mar ga(?:ya|yi)|nahi rahe)\b",
     ("fresh_grief",)),
    (r"\b(lost (?:my|her|his|our)|death of|kho diya)\b", ("fresh_grief",)),
    (r"\b(dumped|broke up|broken up|breakup|break-up|divorce|separated)\b",
     ("breakup",)),
    (r"\b(left me|cheated on me|chhod diya|chod diya|dhoka|talaaq)\b", ("breakup",)),
]

_FELT_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    (r"\b(grief|grieving|bereave|mourn|loss)\b", ("fresh_grief",)),
    (r"\b(heartbreak|broken heart|dil toot|dil tuta)\b", ("breakup",)),
    (r"\b(anxious|anxiety|panic|restless|bechain|pareshan)\b", ("active_anxiety",)),
    (r"\b(lonely|alone|akela|tanha|isolated)\b", ("loneliness",)),
]

_DESTINATION_STATES: dict[str, tuple[str, ...]] = {
    "lift_gently": ("wants_cheering",),
    "sleep": ("sleep_seeking",),
    "escape": ("low_attention",),
}


def _match(text: str, patterns: list[tuple[str, tuple[str, ...]]]) -> set[str]:
    low = text.lower()
    found: set[str] = set()
    for pattern, codes in patterns:
        if re.search(pattern, low):
            found.update(codes)
    return found


def derive_content_codes(contraindicated_for: Iterable[str]) -> frozenset[str]:
    """Index time. Free-text contraindications -> closed codes.

    Run once per fingerprint during indexing, never in the query path.
    """
    codes: set[str] = set()
    for phrase in contraindicated_for:
        codes.update(_match(phrase, _TEXT_PATTERNS))
    return frozenset(codes)


GATED_CODES = frozenset({"fresh_grief", "breakup"})
INTENSITY_GATE = 0.45

# --------------------------------------------------------------------------
# Structural safety net — the axis rule
# --------------------------------------------------------------------------
# The code vocabulary above can only block what the fingerprinter thought to
# WRITE DOWN, and it writes free prose. In the seed catalog that gap is visible:
# all three trap arcs are equally harmful to a grieving listener, but only one
# happens to say "raw grief" in its contraindications, so the other two were
# reachable by anyone whose state parsed as `fresh_grief` rather than `breakup`.
# Grief and heartbreak are not the same state and the vocabulary correctly keeps
# them apart -- but "content shaped like despair" is harmful to both, and relying
# on an LLM to have enumerated every raw state per arc is the wrong mechanism.
#
# So: a second, structural rule over the axes, which are always present and
# never prose. A listener in a raw state is not served despair-shaped content
# even when nobody wrote a contraindication for it. PRD §9 claims exactly this
# ("enforced at retrieval, not just at the LLM layer"); this is what makes it
# true.
#
# All three conditions must hold, which makes the rule narrow on purpose. In the
# seed catalog it separates cleanly with margin on both sides: the traps sit at
# hope <= 0.15, while the most despair-adjacent legitimate neighbourhood
# (`sit_with`) is floored at hope 0.30. Widening any threshold risks emptying the
# one shelf a grieving listener most wants, which is its own harm.
RAW_STATES = frozenset({"fresh_grief", "breakup"})
DESPAIR_HOPE_MAX = 0.20
DESPAIR_VALENCE_MAX = -0.50
DESPAIR_WEIGHT_MIN = 0.75


def is_despair_shaped(axes) -> bool:
    """Hopeless AND bleak AND heavy. Not "sad" -- sad is what they came for."""
    return (
        axes.hope <= DESPAIR_HOPE_MAX
        and axes.valence <= DESPAIR_VALENCE_MAX
        and axes.weight >= DESPAIR_WEIGHT_MIN
    )


def in_raw_state(listener_codes: frozenset[str]) -> bool:
    """True when the axis rule should apply on top of the code vocabulary."""
    return bool(listener_codes & RAW_STATES)


def derive_listener_codes(query: MoodQuery) -> frozenset[str]:
    """Query time. Parsed query -> the states this listener is in.

    THE BUG THIS FIXES, because it is subtle and it mattered:

    The intensity gate used to drop `fresh_grief`/`breakup` from *all* evidence
    whenever `intensity < 0.45`. Reasonable-looking, and it disabled the safety
    layer on precisely the rawest inputs -- because `heuristic_parse` scores
    intensity from its felt-word list, and phrases like "just got dumped" or "my
    grandmother died" contain none of those words. They parsed at intensity 0.3,
    the gate stripped the code, and the trap arcs sailed through. The two most
    acute queries in the eval set were the two with no protection, and the
    trap-avoidance metric still read ~100% because the destination axis filters
    happened to exclude those arcs for unrelated reasons.

    So the gate now applies only to MOOD evidence. If the listener named an
    EVENT, the code stands regardless of how the parser scored intensity -- a
    death does not become less of a contraindication because the sentence
    describing it was calm.
    """
    event_codes = (
        _match(" ".join(query.felt_state), _EVENT_PATTERNS)
        | _match(query.raw_text, _EVENT_PATTERNS)
    )
    mood_codes = (
        _match(" ".join(query.felt_state), _FELT_PATTERNS)
        | _match(query.raw_text, _FELT_PATTERNS)
    )

    # Mild feelings are not contraindications. Someone mildly wistful does not
    # need protecting from a sad story -- over-blocking empties shelves and is
    # its own failure. An event is not a feeling, so it is never gated.
    if query.intensity < INTENSITY_GATE:
        mood_codes -= GATED_CODES

    codes = event_codes | mood_codes

    if query.destination:
        codes.update(_DESTINATION_STATES.get(query.destination, ()))

    if query.situation.activity:
        codes.update(_match(query.situation.activity, _TEXT_PATTERNS) & {"low_attention"})

    return frozenset(codes)


def event_codes_in(text: str) -> frozenset[str]:
    """Does this text name a concrete loss/rupture event (not just a feeling)?

    Public so the parser can share this one lexicon instead of keeping a second,
    drifting copy. The parser uses it to raise `intensity`; retrieval uses it to
    decide what the intensity gate may not touch.
    """
    return frozenset(_match(text, _EVENT_PATTERNS))


def is_blocked(
    content_codes: frozenset[str],
    listener_codes: frozenset[str],
) -> tuple[bool, str | None]:
    """Set intersection. Returns (blocked, first offending code)."""
    hit = content_codes & listener_codes
    if hit:
        return True, sorted(hit)[0]
    return False, None


def explain_block(code: str) -> str:
    """Human-readable reason. Surfaced in eval output and debug UI, never to
    the listener -- telling someone why we hid something is its own harm."""
    return {
        "fresh_grief": "flagged as wrong for raw grief",
        "breakup": "flagged as wrong for a fresh breakup",
        "wants_cheering": "flagged as wrong for someone wanting to be lifted",
        "active_anxiety": "flagged as wrong for an anxious listener",
        "loneliness": "flagged as wrong for someone feeling alone",
        "sleep_seeking": "flagged as wrong for winding down",
        "low_attention": "needs more attention than this listener has",
    }.get(code, code)
