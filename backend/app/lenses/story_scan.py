"""Story-scoped contradiction scan — the "Plot Holes as a book" lens.

The graph-grounded Plot Hole Hunter (``plot_holes.py``) traverses the whole
persisted canon, so it also surfaces the seeded ANDHERA demo. This lens instead
reads ONE loaded show directly from its episode scripts and reports the
cross-episode contradictions *within that story only* — nothing from the graph,
nothing from the seed. Because it sees the raw episode text (which the graph
never stores), it can return the exact verbatim sentence on each side, so the UI
can highlight the clashing lines like a book.
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel

from app.config import settings
from app.llm.factory import get_llm
from app.schemas import StoryContradiction, StoryScanRequest, StoryScanResult

logger = logging.getLogger(__name__)

# Max contradictions to return — keep the book view focused on the strongest.
_MAX_CONTRADICTIONS = 8
# Strip a leading "Scene 3:" prefix if the model copies it into a quote.
_SCENE_PREFIX = re.compile(r"^\s*Scene\s+\d+\s*:\s*", re.IGNORECASE)


class _Contradictions(BaseModel):
    """Private LLM output wrapper."""

    contradictions: list[StoryContradiction]


_SYSTEM = (
    "You are a continuity editor for a serialized audio drama. You are given the FULL "
    "script of every episode of ONE show. Build the show's canon in your head — the "
    "atomic facts about characters, places, objects, dates and numbers — then find "
    "CONTRADICTIONS: the same subject and attribute given DIFFERENT, incompatible values "
    "in DIFFERENT episodes (e.g. a building's floor count, a character's whereabouts on a "
    "date, an object's status, a year, an age, a count). "
    "For each contradiction return: `subject` (what disagrees, e.g. 'Flat 6B — status'), "
    "a `severity` (high/medium/low), a short plain-language `detail` explaining the clash, "
    "a concrete `fix`, and for EACH side the episode label (`episode_a`/`episode_b`) and "
    "the EXACT VERBATIM SENTENCE from that episode (`quote_a`/`quote_b`). Copy each quote "
    "exactly as written — a single complete sentence — and do NOT include any 'Scene N:' "
    "prefix. Only report genuine contradictions grounded in the supplied text; never invent "
    "facts, and never pair a value with itself. Order most severe first; return at most "
    f"{_MAX_CONTRADICTIONS}."
)


def _clean_quote(q: str) -> str:
    return _SCENE_PREFIX.sub("", (q or "").strip()).strip()


def _render_corpus(req: StoryScanRequest) -> tuple[str, int]:
    """Concatenate every non-empty episode, labelled, for the prompt."""
    blocks: list[str] = []
    for ep in req.episodes:
        if ep.text and ep.text.strip():
            blocks.append(f"=== {ep.episode} ===\n{ep.text.strip()}")
    return "\n\n".join(blocks), len(blocks)


async def scan_story(req: StoryScanRequest) -> StoryScanResult:
    """Detect cross-episode contradictions within a single loaded show."""
    corpus, n = _render_corpus(req)
    # Need at least two episodes for a *cross-episode* contradiction to exist.
    if n < 2:
        return StoryScanResult(contradictions=[], episodes_scanned=n)

    prompt = (
        f"SHOW: {req.title}\n\n"
        f"Below are all {n} episodes of this show, in order. Read every one, then list the "
        f"cross-episode continuity contradictions.\n\n{corpus}"
    )

    llm = get_llm()
    res = await llm.structured(
        system=_SYSTEM,
        prompt=prompt,
        schema=_Contradictions,
        model=settings.model_for("experts"),
    )

    cleaned: list[StoryContradiction] = []
    for c in res.contradictions:
        qa, qb = _clean_quote(c.quote_a), _clean_quote(c.quote_b)
        # Drop degenerate rows: missing quotes or a value paired with itself.
        if not qa or not qb or qa == qb:
            continue
        cleaned.append(c.model_copy(update={"quote_a": qa, "quote_b": qb}))
        if len(cleaned) >= _MAX_CONTRADICTIONS:
            break

    return StoryScanResult(contradictions=cleaned, episodes_scanned=n)
