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

from schemas import MoodQuery

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
_FELT_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    (r"\b(grief|grieving|bereave|mourn|loss)\b", ("fresh_grief",)),
    (r"\b(heartbreak|breakup|break-up|dumped|divorce)\b", ("breakup",)),
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


def derive_listener_codes(query: MoodQuery) -> frozenset[str]:
    """Query time. Parsed query -> the states this listener is in."""
    codes: set[str] = set()

    codes.update(_match(" ".join(query.felt_state), _FELT_PATTERNS))
    codes.update(_match(query.raw_text, _FELT_PATTERNS))

    if query.destination:
        codes.update(_DESTINATION_STATES.get(query.destination, ()))

    if query.situation.activity:
        codes.update(_match(query.situation.activity, _TEXT_PATTERNS) & {"low_attention"})

    # Low-intensity states are not contraindications. Someone mildly wistful
    # does not need protecting from a sad story -- over-blocking empties
    # shelves and is its own failure. Only guard when it is actually raw.
    if query.intensity < 0.45:
        codes -= {"fresh_grief", "breakup"}

    return frozenset(codes)


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
