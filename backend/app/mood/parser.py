"""
Mood-First Search — query parser. PRD §8.2 stage 1.

Replaces `fake_parse`. Same signature, same return type, so api.py changes by
one import.

WHY THE FALLBACK IS NOT OPTIONAL
--------------------------------
The parser sits at the very front of the request. If it throws, there is no
degraded experience -- there is a blank screen. So every failure path lands on
the heuristic: no key, no network, quota exhausted, malformed JSON, a schema
the model decided to improvise on. The heuristic is genuinely worse at nuance
and genuinely fine at the hero query, which is the correct trade for a path
that must never be down.

DISTRESS DETECTION IS DELIBERATELY NOT LEFT TO THE LLM
------------------------------------------------------
`distress_flag` is computed by keyword rules BEFORE the model runs, and the
model can only ever set it to True -- never clear it. A false positive costs a
listener one gentle screen they can tap past. A false negative routes someone
in crisis into a shelf of despair-adjacent fiction. Those errors are not
symmetric, so the cheap deterministic check owns the floor and the model is
allowed to add to it, never subtract.
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional

from app.mood.contraindications import event_codes_in
from app.mood.mood_config import heuristic_sparsity
from app.mood.llm_client import LLMClient
from app.mood.schemas import SPARSITY_THRESHOLD, Destination, MoodQuery, Situation

# Explicit, high-precision. Not an exhaustive list and not meant to be -- the
# LLM widens recall on top of this; these are the ones we refuse to miss.
DISTRESS_PATTERNS = (
    r"\bkill myself\b", r"\bend it all\b", r"\bwant to die\b", r"\bself[- ]harm\b",
    r"\bno reason to live\b", r"\bstop existing\b", r"\bdisappear forever\b",
    r"\bstop feeling anything\b", r"\bmarna hai\b", r"\bjeene ka mann nahi\b",
    r"\bkhatam kar (?:doon|du)\b", r"\bzinda nahi rehna\b",
)

_DESTINATIONS = (
    "sit_with", "lift_gently", "company", "escape", "make_sense_of", "sleep",
)

# Floor applied when the text names a concrete loss/rupture event. Above the
# contraindication intensity gate (0.45) with room to spare, and high enough that
# `resolve_target` asks for noticeably more warmth and companionship.
EVENT_INTENSITY_FLOOR = 0.75

SYSTEM = """\
You convert a listener's free-text description of how they want something to \
feel into a structured query. You are not recommending anything.

Return ONLY a JSON object, no prose, no markdown fences:
{
  "situation": {"time_of_day": null|str, "weather": null|str,
                "solitude": "alone"|"with_others"|"unknown",
                "activity": null|str, "place": null|str},
  "felt_state": [str],
  "intensity": 0.0-1.0,
  "destination": null|"sit_with"|"lift_gently"|"company"|"escape"|"make_sense_of"|"sleep",
  "intensity_tolerance": 0.0-1.0,
  "session_length_min": null|int,
  "language": "en",
  "avoid_tags": [str],
  "sparsity_score": 0.0-1.0,
  "distress": true|false
}

Guidance:
- "destination" is what they want the listening to DO for them. Set it null \
whenever the text genuinely supports more than one reading -- null is the \
common case and it is correct. Only commit when they said it.
- "sparsity_score" is how little emotional signal the text carries. \
"bore ho raha hoon" is ~0.9. A sentence naming a feeling and a situation is \
~0.1. This decides whether we ask a question instead of guessing.
- "felt_state" holds emotions, not topics. "heartbreak" yes; "romance" no.
- "intensity" is how raw this is right now, not how strong the words are.
- Set "distress" true only for self-harm intent or wanting to stop existing. \
Ordinary sadness, grief and heartbreak are NOT distress.
- Hinglish is expected. Read it; do not translate the felt_state into \
formal English if the listener's own word is more precise.\
"""


def detect_distress(text: str) -> bool:
    low = text.lower()
    return any(re.search(p, low) for p in DISTRESS_PATTERNS)


def _clamp(v, lo=0.0, hi=1.0, default=0.5) -> float:
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return default


def heuristic_parse(text: str) -> MoodQuery:
    """Deterministic floor. Runs when the LLM is unavailable, and always for
    distress. Keyword-level only -- it will miss nuance and that is understood."""
    low = text.lower()

    felt = [w for w in (
        "heartbreak", "breakup", "lonely", "sad", "tired", "numb", "angry",
        "anxious", "empty", "restless", "nostalgic", "akela", "udaas", "thaka",
        "bechain", "tanha", "dukhi", "bore",
    ) if w in low]

    # An event ("she died", "just got dumped") is stronger evidence of a raw
    # state than any mood adjective, and it frequently arrives with NO mood word
    # at all -- which used to parse as intensity 0.3 and quietly disable the
    # contraindication layer downstream. Named events carry their own codes into
    # felt_state and set intensity high.
    events = event_codes_in(text)
    felt.extend(code for code in sorted(events) if code not in felt)

    destination: Optional[Destination] = None
    if any(w in low for w in ("sona", "neend", "sleep", "bedtime", "so jaun")):
        destination = "sleep"
    elif any(w in low for w in ("drive", "commute", "jagaye", "safar", "long ride")):
        destination = "escape"
    elif any(w in low for w in ("saath", "company", "akela", "koi awaaz")):
        destination = "company"
    elif any(w in low for w in ("halka", "light", "cheer", "khush")):
        destination = "lift_gently"

    return MoodQuery(
        raw_text=text,
        situation=Situation(
            weather=("rain" if any(w in low for w in ("rain", "baarish", "monsoon", "saawan")) else None),
            time_of_day=("night" if any(w in low for w in ("night", "raat", "2 baje")) else
                         "morning" if any(w in low for w in ("morning", "subah")) else None),
            solitude=("alone" if any(w in low for w in ("alone", "akela", "tanha", "kisi se baat nahi")) else "unknown"),
            activity=("driving" if any(w in low for w in ("drive", "driving", "safar")) else None),
        ),
        felt_state=felt,
        intensity=0.85 if events else (0.7 if felt else 0.3),
        destination=destination,
        sparsity_score=heuristic_sparsity(text),
        distress_flag=detect_distress(text),
    )


def _from_json(text: str, payload: dict) -> MoodQuery:
    sit = payload.get("situation") or {}
    dest = payload.get("destination")
    if dest not in _DESTINATIONS:
        dest = None

    # The model may raise distress; it may never lower it.
    distress = detect_distress(text) or bool(payload.get("distress", False))

    # Same asymmetry for intensity: a named event floors it. Models routinely
    # read a flatly-worded "my mother died last week" as low intensity because
    # the *sentence* is calm, and intensity now steers how much holding the
    # target asks for. The model can raise this; it cannot talk it down.
    intensity = _clamp(payload.get("intensity"), default=0.5)
    if event_codes_in(text):
        intensity = max(intensity, EVENT_INTENSITY_FLOOR)

    return MoodQuery(
        raw_text=text,
        situation=Situation(
            time_of_day=sit.get("time_of_day"),
            weather=sit.get("weather"),
            solitude=sit.get("solitude") if sit.get("solitude") in
            ("alone", "with_others", "unknown") else "unknown",
            activity=sit.get("activity"),
            place=sit.get("place"),
        ),
        felt_state=[str(f) for f in (payload.get("felt_state") or [])][:6],
        intensity=intensity,
        destination=dest,
        intensity_tolerance=_clamp(payload.get("intensity_tolerance"), default=0.5),
        session_length_min=payload.get("session_length_min"),
        language=payload.get("language") or "en",
        avoid_tags=[str(t) for t in (payload.get("avoid_tags") or [])][:8],
        sparsity_score=_clamp(payload.get("sparsity_score"),
                              default=heuristic_sparsity(text)),
        distress_flag=distress,
    )


def _extract_json(raw: str) -> dict:
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in parser output")
    return json.loads(raw[start:end + 1])


class MoodParser:
    def __init__(self, client: Optional[LLMClient] = None) -> None:
        self.client = client

    def parse(self, text: str) -> MoodQuery:
        text = (text or "").strip()
        if not text:
            return MoodQuery(raw_text="", sparsity_score=1.0)

        if self.client is None:
            return heuristic_parse(text)

        try:
            raw = self.client.complete(SYSTEM, f'Listener said: "{text}"')
            query = _from_json(text, _extract_json(raw))
        except Exception:
            return heuristic_parse(text)

        # Sanity floor: if the model returned a confident destination on text
        # the heuristic reads as near-empty, distrust it. A confident answer to
        # "bore ho raha hoon" is the model inventing intent, and the cost of
        # that is a wrong shelf instead of a question we should have asked.
        if query.destination and query.sparsity_score < SPARSITY_THRESHOLD:
            if heuristic_sparsity(text) > 0.85:
                query = query.model_copy(
                    update={"destination": None, "sparsity_score": 1.0}
                )
        return query


def default_parser() -> MoodParser:
    from app.mood.llm_client import default_client

    return MoodParser(default_client(max_tokens=600))
