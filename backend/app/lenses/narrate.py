"""Narration lens — voice the two Cliffhanger endings for an audible A/B.

PocketFM is an audio platform, so the hook-score lift shouldn't only be a number:
this renders the weak *original* ending read flat and passive, and the *optimized*
cliffhanger read with dramatic, in-character tension. Same words — the delivery is
the point.

Both clips are returned as base64 in one response so the UI can preload the whole
A/B, and each clip is cached by text hash so repeat demos are instant and
quota-free.
"""

from __future__ import annotations

import asyncio
import base64
import re

from app.config import settings
from app.engine.cache import Cache
from app.llm import tts
from app.schemas import NarrationClip, NarrationResult

# Two deliberately opposite deliveries. The contrast is what makes +15 audible.
_FLAT_STYLE = (
    "Read the following passage aloud in a soft but flat, disengaged, monotone "
    "voice. Keep even pacing, no dramatic pauses and no emphasis, as if reading a "
    "memo out loud."
)
_DRAMATIC_STYLE = (
    "You are a soft-spoken young woman narrating the climax of a gripping audio "
    "drama. Stay in character with a soft, intimate, breathy delivery: let the "
    "tension build, slow down and drop almost to a whisper on the final reveal, and "
    "land the last line as a cliffhanger hook that makes the listener need the next "
    "episode."
)


async def _clip(
    text: str,
    *,
    style_label: str,
    voice: str,
    rate: float,
    gemini_style: str,
    cache: Cache,
) -> NarrationClip:
    """Synthesize (or replay from cache) one narrated ending."""
    text = (text or "").strip()
    # Drop a leading scene label ("Scene 8:" / "दृश्य 8:") so the narration reads
    # the line itself, not the marker.
    text = re.sub(r"^\s*(scene|दृश्य)\s*\d+\s*[:：.\-–—]\s*", "", text, flags=re.IGNORECASE)
    text = text[: settings.tts_max_chars]
    if not text:
        # Nothing to voice — return a silent placeholder rather than erroring the
        # pair, so the other clip still plays.
        return NarrationClip(audio_base64="", style=style_label, voice=voice)

    key = cache.make_key(
        "tts",
        settings.tts_engine,
        settings.tts_model,
        settings.tts_language_code,
        style_label,
        voice,
        text,
    )
    cached = cache.get(key)
    if cached:
        return NarrationClip(**cached)

    result = await tts.synth(text, voice=voice, rate=rate, gemini_style=gemini_style)
    clip = NarrationClip(
        audio_base64=base64.b64encode(result.audio).decode("ascii"),
        mime=result.mime,
        voice=result.voice,
        engine=result.engine,
        style=style_label,
        duration_ms=0,
    )
    cache.set(key, clip.model_dump())
    return clip


async def run_narration(original: str, optimized: str) -> NarrationResult:
    """Voice both endings concurrently and return them as an audible A/B."""
    cache = Cache(settings.cache_dir)
    flat, dramatic = await asyncio.gather(
        _clip(
            original,
            style_label="flat",
            voice=settings.tts_voice_flat,
            rate=settings.tts_rate_flat,
            gemini_style=_FLAT_STYLE,
            cache=cache,
        ),
        _clip(
            optimized,
            style_label="dramatic",
            voice=settings.tts_voice_dramatic,
            rate=settings.tts_rate_dramatic,
            gemini_style=_DRAMATIC_STYLE,
            cache=cache,
        ),
    )
    return NarrationResult(original=flat, optimized=dramatic)
