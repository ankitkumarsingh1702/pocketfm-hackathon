"""LLM extraction of story-canon entities, relations, and facts from an episode.

Uses the same structured-output choke point as every other agent
(``llm.structured`` on Vertex). Best-effort: any failure yields an empty
``CanonExtraction`` so ingestion never breaks a run.
"""

from __future__ import annotations

import logging

from app.config import settings
from app.llm.base import LLMClient
from app.schemas import CanonExtraction, Story

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a story-continuity analyst building the canon graph for a serialized "
    "audio drama. Extract the durable things a returning listener would remember.\n\n"
    "Return three lists:\n"
    "- entities: characters, locations, clues, plot_threads (open mysteries/arcs), "
    "and themes. Give each a short lowercase `key` (used to reference it in "
    "relations), a `type`, a canonical `name`, and a one-line `description`.\n"
    "- relations: directed edges between entities BY KEY, with an UPPER_SNAKE_CASE "
    "`type` such as APPEARS_IN, LOCATED_AT, SUSPECTS, INTRODUCES, FORESHADOWS, "
    "RELATED_TO.\n"
    "- facts: atomic, checkable claims for continuity checking, as "
    "(subject_key, predicate, object). Prefer concrete, falsifiable facts — counts, "
    "dates, states, locations (e.g. subject 'building', predicate 'floor_count', "
    "object '5'). These are how contradictions are later detected.\n\n"
    "Only extract what the script actually supports. Be precise and concise."
)


def _story_text(story: Story) -> str:
    """Compact prompt-friendly rendering of a story."""
    episode = story.episode or "-"
    return f"TITLE: {story.title}\nEPISODE: {episode}\nSCRIPT:\n{story.text}"


async def extract_canon(
    story: Story, llm: LLMClient, model: str | None = None
) -> CanonExtraction:
    """Extract the story canon from one episode. Empty on any failure.

    ``model`` lets the non-persisting live preview use the faster audience
    model; durable ingest keeps the stronger expert model by default.
    """
    try:
        return await llm.structured(
            system=_SYSTEM,
            prompt="Extract the story canon from this episode.\n\n" + _story_text(story),
            schema=CanonExtraction,
            model=model or settings.model_for("experts"),
        )
    except Exception as exc:  # noqa: BLE001 - extraction is strictly best-effort
        logger.warning("Canon extraction failed: %s", exc)
        return CanonExtraction()
