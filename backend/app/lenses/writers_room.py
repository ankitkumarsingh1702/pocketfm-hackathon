"""Writers' Room lens — a panel of expert personas critiques one episode.

Each expert (director, editor, sound designer, ...) is asked for a structured
craft critique concurrently. Consensus is summarised locally (no extra LLM
call) from the panel's verdicts, scores, and most-cited issue.
"""

from __future__ import annotations

import asyncio
from collections import Counter

from app.db.firestore import save_simulation
from app.llm.factory import get_llm
from app.personas.loader import load_personas
from app.schemas import ExpertFeedback, ExpertNote, Story, WritersRoomResult


def _story_text(story: Story) -> str:
    """Render a story into a compact prompt-friendly block."""
    episode = story.episode or "-"
    return f"TITLE: {story.title} EPISODE: {episode} SCRIPT:\n{story.text}"


def _consensus(panel: list[ExpertFeedback]) -> str:
    """Summarise the panel locally: verdict counts, avg score, top issue."""
    if not panel:
        return "No expert feedback was available for this episode."

    n = len(panel)
    verdicts = Counter(fb.note.verdict for fb in panel)
    verdict_parts = ", ".join(f"{count} {verdict}" for verdict, count in verdicts.most_common())
    avg_score = sum(fb.note.score for fb in panel) / n

    issues = Counter(
        issue.strip().lower()
        for fb in panel
        for issue in fb.note.issues
        if issue.strip()
    )
    theme = ""
    if issues:
        top_issue, _ = issues.most_common(1)[0]
        theme = f' The most-cited concern is "{top_issue}".'

    return f"Panel of {n}: {verdict_parts}; average score {avg_score:.0f}/100.{theme}"


async def run_writers_room(story: Story) -> WritersRoomResult:
    """Collect expert critiques of `story` and build a consensus summary."""
    experts = load_personas("expert")
    llm = get_llm()

    prompt = "Critique this audio-drama episode for craft.\n" + _story_text(story)
    notes = await asyncio.gather(
        *(llm.structured(system=e.system_prompt, prompt=prompt, schema=ExpertNote) for e in experts),
        return_exceptions=True,
    )

    panel: list[ExpertFeedback] = []
    for expert, note in zip(experts, notes):
        if isinstance(note, Exception):
            continue  # drop experts whose call failed
        panel.append(ExpertFeedback(persona=expert.name, role=expert.role or "Expert", note=note))

    result = WritersRoomResult(panel=panel, consensus=_consensus(panel))
    save_simulation("writers_room", story, result.model_dump())
    return result
