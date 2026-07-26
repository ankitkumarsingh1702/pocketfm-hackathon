"""
Mood-First Search — reranking.

ONE CALL, TWO OUTPUTS
---------------------
The reranker returns a score AND the explanation line. Not two calls, one.

That is a correctness decision, not a cost saving. If a separate pass writes
the explanation, it is writing a justification for a ranking it did not make --
it will confabulate a plausible reason that has nothing to do with why the item
actually placed. Asking the same pass to commit to a reason forces the score
and the reason to come from one act of judgement, and it makes bad rankings
visible: a weak reason is a reliable tell that the retrieval underneath was
weak.

The explanation is also the single most-quoted artifact in the demo, so it is
worth the constraint.

CONTRAINDICATIONS ARE CHECKED TWICE
-----------------------------------
The closed-vocab block in retrieval already ran. The reranker checks again in
free text, because the code vocabulary is finite and content can be wrong for a
listener in ways nobody enumerated. Retrieval's check is the floor, not the
ceiling. The reranker may only REMOVE items -- it can never reinstate one that
retrieval blocked.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Optional, Protocol, Sequence

from app.mood.contraindications import (
    derive_content_codes,
    derive_listener_codes,
    in_raw_state,
    is_blocked,
    is_despair_shaped,
)
from app.mood.schemas import Destination, MoodQuery
from app.mood.store import Candidate

MAX_EXPLANATION_CHARS = 120


@dataclass(slots=True)
class RerankedItem:
    candidate: Candidate
    score: float           # 0..1
    explanation: str
    dropped: bool = False
    drop_reason: Optional[str] = None


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class AnthropicClient:
    """Thin wrapper. Kept minimal on purpose -- swapping providers should be a
    constructor change, not a refactor."""

    def __init__(self, model: str = "claude-sonnet-4-6", max_tokens: int = 2000) -> None:
        import anthropic  # lazy

        self._client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, system: str, user: str) -> str:
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in msg.content if b.type == "text")


SYSTEM = """\
You judge whether a piece of audio fiction delivers a specific felt experience \
to a listener in a specific emotional state. You are not judging quality, \
popularity, or plot. Only: will this feel the way they asked for.

Rules:
- Score 0-10. 10 means a listener in this exact state would feel understood.
- Lexical overlap is a trap. A story ABOUT rain and heartbreak is often the \
worst possible answer for someone IN heartbreak. Reward emotional fit, not \
topical fit.
- Set "harmful": true if this would make their state worse, however good the \
match otherwise looks. This overrides the score.
- "reason" is ONE short line spoken to the listener, under 120 characters. \
Their emotional register, never metadata. No plot spoilers. No genre words. \
No "this show is" or "fans of". Address the feeling, not the file.

Return ONLY a JSON array, no prose, no markdown fences:
[{"id": 0, "score": 8, "harmful": false, "reason": "..."}]\
"""


def build_user_prompt(
    query: MoodQuery, destination: Destination, candidates: Sequence[Candidate]
) -> str:
    state = ", ".join(query.felt_state) or "unstated"
    sit = {k: v for k, v in query.situation.model_dump().items() if v and v != "unknown"}

    lines = [
        f'Listener said: "{query.raw_text}"',
        f"Felt state: {state} (intensity {query.intensity:.1f})",
        f"Situation: {sit or 'none given'}",
        f"What they want from this: {destination}",
        "",
        "Candidates:",
    ]
    for i, c in enumerate(candidates):
        fp = c.fingerprint
        lines.append(
            f'{i}. "{fp.vibe_sentence}"'
            f" | good for: {', '.join(fp.good_for) or '—'}"
            f" | wrong for: {', '.join(fp.contraindicated_for) or '—'}"
            f" | tone: valence {fp.axes.valence:+.1f}, warmth {fp.axes.warmth:.1f},"
            f" catharsis {fp.axes.catharsis:.1f}, pace {fp.axes.pace:.1f}"
        )
    return "\n".join(lines)


def _parse(raw: str) -> list[dict]:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("no JSON array in reranker output")
    return json.loads(raw[start:end + 1])


class LLMReranker:
    def __init__(self, client: LLMClient, fallback: "HeuristicReranker | None" = None) -> None:
        self.client = client
        self.fallback = fallback or HeuristicReranker()

    def rerank(
        self, query: MoodQuery, destination: Destination, candidates: Sequence[Candidate]
    ) -> list[RerankedItem]:
        if not candidates:
            return []
        try:
            raw = self.client.complete(SYSTEM, build_user_prompt(query, destination, candidates))
            judged = _parse(raw)
        except Exception:
            # Any failure -- network, quota, malformed JSON -- degrades to the
            # heuristic rather than taking the shelf down. Demo day rule.
            return self.fallback.rerank(query, destination, candidates)

        by_id = {int(j["id"]): j for j in judged if "id" in j}
        out: list[RerankedItem] = []
        for i, cand in enumerate(candidates):
            j = by_id.get(i)
            if j is None:
                continue
            harmful = bool(j.get("harmful", False))
            reason = str(j.get("reason", "")).strip()[:MAX_EXPLANATION_CHARS]
            out.append(
                RerankedItem(
                    candidate=cand,
                    score=max(0.0, min(1.0, float(j.get("score", 0)) / 10.0)),
                    explanation=reason or _template_reason(destination, cand),
                    dropped=harmful,
                    drop_reason="reranker flagged as harmful" if harmful else None,
                )
            )
        out.sort(key=lambda r: r.score, reverse=True)
        return out


_REASONS: dict[str, tuple[str, ...]] = {
    "sit_with": (
        "Because you didn't ask to feel better — you asked to feel it properly.",
        "This one sits down next to it instead of trying to fix it.",
        "Slow, and it never once tells you to cheer up.",
    ),
    "lift_gently": (
        "Warm without being loud about it.",
        "It lifts, but it doesn't yank.",
        "Light on its feet, and it doesn't ask much of you.",
    ),
    "company": (
        "Mostly it's just a voice that stays.",
        "Low stakes, close mic — like someone in the room.",
        "Nothing happens, pleasantly. That's the point.",
    ),
    "escape": (
        "Far enough from here that you'll forget to check the time.",
        "It picks you up in the first two minutes and doesn't put you down.",
        "A world with its own weather.",
    ),
    "make_sense_of": (
        "It puts a shape around the thing you can't name yet.",
        "Someone else thought this through, carefully.",
        "Not answers exactly — better questions, asked kindly.",
    ),
    "sleep": (
        "Dark, slow, and it never raises its voice.",
        "Built to be half-heard.",
        "Nothing in it will jolt you awake.",
    ),
}
# Every pool needs at least RESULTS_PER_SHELF entries or a shelf is guaranteed to
# repeat a line, which reads as the system having one thought. Asserted in tests.
MIN_REASONS_PER_DESTINATION = 3


def _template_reason(destination: Destination, cand: Candidate) -> str:
    """Pick a line for this arc, stably.

    `hash()` on a str is salted by PYTHONHASHSEED, so the previous version chose
    a different line per process -- which made the "deterministic, offline"
    parachute path non-reproducible across restarts, and any screenshot or
    cached demo response impossible to reproduce. blake2b is stable forever.
    """
    pool = _REASONS.get(destination, ("Close to what you described.",))
    digest = hashlib.blake2b(
        cand.fingerprint.content_id.encode(), digest_size=4
    ).digest()
    return pool[int.from_bytes(digest, "little") % len(pool)]


class HeuristicReranker:
    """No LLM. Deterministic, instant, offline.

    This is the CI default and the demo-day parachute. It reuses the retrieval
    score and adds the one thing retrieval can't express: whether the arc's
    stated `good_for` actually names what this listener came for. Explanations
    come from a small template pool keyed by destination -- weaker than the LLM
    line, but never wrong and never embarrassing.
    """

    _GOOD_FOR_HINTS: dict[str, tuple[str, ...]] = {
        "sit_with": ("crying", "grief", "sitting", "heartbreak", "alone"),
        "lift_gently": ("cheer", "lift", "light", "warm", "hope"),
        "company": ("company", "background", "comfort", "cosy", "cozy"),
        "escape": ("binge", "commute", "immersive", "escape", "drive"),
        "make_sense_of": ("think", "reflect", "understand", "process"),
        "sleep": ("sleep", "bedtime", "wind down", "night"),
    }

    def rerank(
        self, query: MoodQuery, destination: Destination, candidates: Sequence[Candidate]
    ) -> list[RerankedItem]:
        hints = self._GOOD_FOR_HINTS.get(destination, ())
        listener_codes = derive_listener_codes(query)
        out: list[RerankedItem] = []
        for cand in candidates:
            fp = cand.fingerprint
            good_for = " ".join(fp.good_for).lower()
            bonus = 0.12 if any(h in good_for for h in hints) else 0.0

            # Second contraindication check. Retrieval already masked these rows,
            # so this should never fire -- which is exactly why it is here. This
            # class is the CI and offline-demo path, and it used to be the one
            # path with NO safety check at all: `dropped` was never assigned, so
            # the module's "checked twice" claim held only when an LLM answered.
            # A belt-and-braces check that costs a set intersection is the right
            # trade for the one failure this system must not produce.
            hit, code = is_blocked(
                derive_content_codes(fp.contraindicated_for), listener_codes
            )
            if not hit and in_raw_state(listener_codes) and is_despair_shaped(fp.axes):
                hit, code = True, "despair_shaped"
            out.append(
                RerankedItem(
                    candidate=cand,
                    score=max(0.0, min(1.0, cand.score + bonus)),
                    explanation=_template_reason(destination, cand),
                    dropped=hit,
                    drop_reason=f"contraindicated ({code})" if hit else None,
                )
            )
        out.sort(key=lambda r: r.score, reverse=True)
        return out


def default_reranker() -> "LLMReranker | HeuristicReranker":
    """LLM if one resolves (Vertex/ADC, then direct key), heuristic otherwise.
    Never raises."""
    from app.mood.llm_client import default_client

    client = default_client()
    return LLMReranker(client) if client is not None else HeuristicReranker()
