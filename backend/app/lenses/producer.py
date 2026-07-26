"""AI Producer lens — four Sarvam sub-agents plan a full audio-drama production.

Given one episode the studio's "producer" runs four distinct agents concurrently
on Sarvam's LLM and combines them into a single production plan:

1. **Voice Casting Director** — casts each speaking character to a Sarvam voice and
   makes the casting *audible* by voicing a short in-character sample line with
   Sarvam TTS (``bulbul:v3``). This is the lively moment: you can play each
   character's voice.
2. **Sound Designer** — designs the episode's ambience and SFX cues.
3. **Pacing Editor** — maps the episode's tempo beat by beat.
4. **Marketing Strategist** — writes the launch plan (logline, titles, hooks, channels).

Each agent emits its own ``agent_done``/``agent_error`` event so the UI shows a live
run log; one agent's failure never aborts the run. Mirrors the emit-callback shape
of :func:`app.lenses.cliffhanger.run_cliffhanger`, so the API route can wrap it with
:func:`app.engine.streaming.ndjson_events`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from app.config import settings
from app.db.firestore import save_simulation
from app.llm.sarvam import get_sarvam_llm, synth_voice
from app.schemas import (
    CastingPlan,
    MarketingPlan,
    PacingPlan,
    ProductionPlanResult,
    SoundDesignPlan,
    Story,
)

logger = logging.getLogger(__name__)


def _noop(_event: dict) -> None:
    """Default emit sink so the lens runs identically with or without streaming."""


# The four sub-agents, in the order the UI renders their placeholders.
_AGENTS: list[dict] = [
    {"id": "casting", "name": "Voice Casting Director", "role": "Casting"},
    {"id": "sound", "name": "Sound Designer", "role": "Sound"},
    {"id": "pacing", "name": "Pacing Editor", "role": "Editing"},
    {"id": "marketing", "name": "Marketing Strategist", "role": "Marketing"},
]

_SCHEMAS = {
    "casting": CastingPlan,
    "sound": SoundDesignPlan,
    "pacing": PacingPlan,
    "marketing": MarketingPlan,
}

_SYSTEM = {
    "casting": (
        "You are an award-winning Voice Casting Director for premium audio dramas at "
        "PocketFM. Read the episode and cast each important speaking character to a "
        "distinct voice. For each character give a vivid one-line voice persona, the "
        "chosen voice id (EXACTLY as listed in ALLOWED VOICES), a one-sentence rationale, "
        "and a short in-character sample line (max ~180 chars) written in the SAME "
        "LANGUAGE as the script. Leave audio_base64 and mime empty — they are filled in "
        "later. Also suggest the narrator's ideal voice in one line."
    ),
    "sound": (
        "You are a masterful Sound Designer for audio dramas. Design this episode's "
        "soundscape: one sentence for the overall ambience, then specific sound-effect / "
        "ambience cues tied to scenes, each with when it enters and the mood it reinforces."
    ),
    "pacing": (
        "You are a sharp Story Editor who controls pacing. Give a one-sentence read on the "
        "episode's pacing, a rough spoken runtime estimate, and a beat-by-beat tempo map "
        "(each beat marked slow, medium, or fast) with a concrete direction per beat."
    ),
    "marketing": (
        "You are a growth-minded Marketing Strategist for a top audio streaming app. From "
        "the episode craft a launch plan: a one-sentence logline, the target audience, "
        "several title options, punchy promo hooks / social captions, the best promotion "
        "channels, and a release-timing suggestion."
    ),
}


def _valid_voice(voice: str) -> str:
    """Snap a model-chosen voice to an allowed Sarvam speaker id (else the first)."""
    allowed = settings.sarvam_voices
    v = (voice or "").strip()
    if v in allowed:
        return v
    low = v.lower()
    for a in allowed:
        if a.lower() == low:
            return a
    return allowed[0] if allowed else v


def _story_prompt(story: Story) -> str:
    """Render the episode into a compact, length-bounded prompt block."""
    text = (story.text or "")[: settings.producer_max_script_chars]
    return f"SHOW: {story.title}\nEPISODE: {story.episode or '-'}\n\nSCRIPT:\n{text}"


def _summary(
    title: str,
    casting: CastingPlan | None,
    sound: SoundDesignPlan | None,
    pacing: PacingPlan | None,
    marketing: MarketingPlan | None,
) -> str:
    """Compose a short producer's memo from whichever agents succeeded (local)."""
    parts: list[str] = []
    if casting and casting.characters:
        parts.append(f"{len(casting.characters)} roles cast")
    if sound and sound.cues:
        parts.append(f"{len(sound.cues)} sound cues")
    if pacing and pacing.beats:
        parts.append(f"{len(pacing.beats)}-beat pacing map")
    if marketing and marketing.title_options:
        parts.append(f"{len(marketing.title_options)} title ideas")
    body = "; ".join(parts) if parts else "no agents completed"
    memo = f"Production plan for “{title}”: {body}."
    if marketing and marketing.logline:
        memo += f" Marketing angle: {marketing.logline}"
    return memo


async def _text_agent(spec: dict, prompt: str, model: str, emit: Callable[[dict], None]):
    """Run one text-only sub-agent; emit its finished event; return (id, result|None)."""
    sarvam = get_sarvam_llm()
    start = time.monotonic()
    try:
        result = await sarvam.structured(
            system=_SYSTEM[spec["id"]], prompt=prompt, schema=_SCHEMAS[spec["id"]], model=model
        )
    except Exception as exc:  # noqa: BLE001 - report as an event, never abort the run
        emit({
            "type": "agent_error",
            "id": spec["id"], "name": spec["name"], "role": spec["role"],
            "error": str(exc),
        })
        return spec["id"], None
    emit({
        "type": "agent_done",
        "id": spec["id"], "name": spec["name"], "role": spec["role"],
        "result": result.model_dump(),
        "elapsed_ms": int((time.monotonic() - start) * 1000),
    })
    return spec["id"], result


async def _casting_agent(prompt: str, language_code: str, model: str, emit: Callable[[dict], None]):
    """Cast characters, then voice a sample line per character with Sarvam TTS."""
    sarvam = get_sarvam_llm()
    spec = _AGENTS[0]
    start = time.monotonic()
    try:
        plan: CastingPlan = await sarvam.structured(
            system=_SYSTEM["casting"], prompt=prompt, schema=CastingPlan, model=model
        )
    except Exception as exc:  # noqa: BLE001
        emit({
            "type": "agent_error",
            "id": "casting", "name": spec["name"], "role": spec["role"],
            "error": str(exc),
        })
        return "casting", None

    # Keep the most important roles, snap each to an allowed voice.
    plan.characters = plan.characters[: settings.producer_max_characters]
    for c in plan.characters:
        c.voice = _valid_voice(c.voice)

    if plan.characters:
        emit({
            "type": "phase", "id": "casting", "status": "tts",
            "detail": f"Rendering {len(plan.characters)} character voices…",
        })
        sem = asyncio.Semaphore(settings.sarvam_tts_concurrency)

        async def _render(character) -> None:
            async with sem:
                try:
                    audio_b64, mime = await synth_voice(
                        character.sample_line, voice=character.voice, language_code=language_code
                    )
                    character.audio_base64, character.mime = audio_b64, mime
                except Exception as exc:  # noqa: BLE001 - one silent voice never fails the run
                    logger.warning(
                        "casting TTS failed for %s (%s): %s", character.name, character.voice, exc
                    )

        await asyncio.gather(*(_render(c) for c in plan.characters))

    rendered = sum(1 for c in plan.characters if c.audio_base64)
    emit({
        "type": "agent_done",
        "id": "casting", "name": spec["name"], "role": spec["role"],
        "result": plan.model_dump(),
        "voices_rendered": rendered,
        "elapsed_ms": int((time.monotonic() - start) * 1000),
    })
    return "casting", plan


async def run_producer(
    story: Story,
    *,
    language_code: str = "en-IN",
    emit: Callable[[dict], None] = _noop,
) -> ProductionPlanResult:
    """Run the four producer sub-agents on ``story`` and combine their plans.

    All four run concurrently on Sarvam; each emits its own ``agent_done`` /
    ``agent_error`` as it lands (casting also emits a ``phase`` while it voices the
    cast). A failed agent is simply dropped from the plan. Returns the combined
    :class:`ProductionPlanResult`; the streaming route wraps this with
    ``ndjson_events`` so a terminal ``done`` carries the same result.
    """
    model = settings.sarvam_llm_model
    base_prompt = _story_prompt(story)
    voices = ", ".join(settings.sarvam_voices)
    casting_prompt = (
        base_prompt
        + f"\n\nALLOWED VOICES (use these speaker ids exactly): {voices}"
        + f"\nCast at most {settings.producer_max_characters} of the most important speaking characters."
    )

    t0 = time.monotonic()
    emit({
        "type": "run_started",
        "agents": _AGENTS,
        "story": {"title": story.title, "episode": story.episode},
    })

    results = await asyncio.gather(
        _casting_agent(casting_prompt, language_code, model, emit),
        _text_agent(_AGENTS[1], base_prompt, model, emit),
        _text_agent(_AGENTS[2], base_prompt, model, emit),
        _text_agent(_AGENTS[3], base_prompt, model, emit),
        return_exceptions=True,
    )

    by_id: dict[str, object] = {}
    for r in results:
        if isinstance(r, Exception):  # a whole coroutine crashed unexpectedly
            logger.warning("producer sub-agent crashed: %s", r)
            continue
        rid, val = r
        if val is not None:
            by_id[rid] = val

    casting = by_id.get("casting")
    sound = by_id.get("sound")
    pacing = by_id.get("pacing")
    marketing = by_id.get("marketing")
    completed = sum(1 for v in (casting, sound, pacing, marketing) if v is not None)
    voices_rendered = sum(1 for c in (casting.characters if casting else []) if c.audio_base64)
    summary = _summary(story.title, casting, sound, pacing, marketing)

    result = ProductionPlanResult(
        show_title=story.title,
        casting=casting,
        sound=sound,
        pacing=pacing,
        marketing=marketing,
        summary=summary,
        agents_completed=completed,
        voices_rendered=voices_rendered,
    )
    emit({
        "type": "orchestrator",
        "summary": summary,
        "agents_completed": completed,
        "voices_rendered": voices_rendered,
        "elapsed_ms": int((time.monotonic() - t0) * 1000),
    })
    save_simulation("producer", story, result.model_dump())
    return result
