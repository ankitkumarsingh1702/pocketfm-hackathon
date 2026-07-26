"""Offline coverage for the AI Producer lens — no network, LLM, or TTS calls.

Verifies the four sub-agents each emit a finished event, the Voice Casting Director
voices its cast via (mocked) Sarvam TTS, invalid voices are snapped to the allowed
set, and the terminal result carries the combined plan with per-character audio.
Also checks that a failed sub-agent is dropped (its error surfaced) without
aborting the run, and that a per-character TTS failure never fails the run.
"""

from __future__ import annotations

import asyncio

from app.config import settings
from app.lenses import producer as lens
from app.lenses.producer import run_producer
from app.schemas import (
    CastingPlan,
    CharacterCasting,
    MarketingPlan,
    PacingBeat,
    PacingPlan,
    SfxCue,
    SoundDesignPlan,
    Story,
)

STORY = Story(title="The Ninth Ring", episode="7", text="A full episode script. The bell rings again.")


class _FakeSarvam:
    """Returns a canned typed plan per requested schema — no network."""

    name = "fake-sarvam"

    async def structured(self, system, prompt, schema, **_kwargs):
        if schema is CastingPlan:
            return CastingPlan(
                characters=[
                    CharacterCasting(
                        name="Naina", persona="anxious lead", voice="ritu",
                        rationale="warm", sample_line="Kaun hai wahan?",
                    ),
                    # An invalid voice the lens must snap to an allowed speaker id.
                    CharacterCasting(
                        name="Ustad", persona="gravelly mentor", voice="NOT_A_VOICE",
                        rationale="deep", sample_line="Sun.",
                    ),
                ],
                narrator_note="calm baritone",
            )
        if schema is SoundDesignPlan:
            return SoundDesignPlan(
                ambience="rain-soaked alley",
                cues=[SfxCue(scene="Opening", cue="thunder", timing="cold open", mood="dread")],
            )
        if schema is PacingPlan:
            return PacingPlan(
                overall="slow burn", runtime_estimate="18-20 min",
                beats=[PacingBeat(section="Hook", tempo="fast", note="open on the scream")],
            )
        if schema is MarketingPlan:
            return MarketingPlan(
                logline="A bell that rings for the dead.", target_audience="thriller fans",
                title_options=["The Ninth Bell"], hooks=["Don't listen alone."],
                channels=["Instagram Reels"], release_note="Fri drop",
            )
        raise AssertionError(f"unexpected schema {schema}")


async def _fake_synth_voice(text, *, voice, language_code):
    return f"AUDIO::{voice}::{text[:6]}", "audio/wav"


def _patch(monkeypatch):
    monkeypatch.setattr(lens, "get_sarvam_llm", lambda: _FakeSarvam())
    monkeypatch.setattr(lens, "synth_voice", _fake_synth_voice)
    monkeypatch.setattr(lens, "save_simulation", lambda *a, **k: None)


def test_producer_emits_four_agents_and_voices_casting(monkeypatch):
    _patch(monkeypatch)
    events: list[dict] = []
    result = asyncio.run(run_producer(STORY, language_code="hi-IN", emit=events.append))

    types = [e["type"] for e in events]
    assert types[0] == "run_started"
    assert len(events[0]["agents"]) == 4

    done = [e for e in events if e["type"] == "agent_done"]
    assert {e["id"] for e in done} == {"casting", "sound", "pacing", "marketing"}

    # Casting emitted a rendering phase and voiced both characters (mocked TTS).
    assert any(e["type"] == "phase" and e["id"] == "casting" for e in events)
    casting_done = next(e for e in done if e["id"] == "casting")
    assert casting_done["voices_rendered"] == 2

    # Terminal result carries the combined plan, audio, and validated voices.
    assert result.agents_completed == 4
    assert result.voices_rendered == 2
    assert result.casting.characters[0].audio_base64.startswith("AUDIO::ritu")
    assert result.casting.characters[1].voice in settings.sarvam_voices  # snapped from NOT_A_VOICE
    assert result.sound.cues[0].cue == "thunder"
    assert result.pacing.beats[0].tempo == "fast"
    assert result.marketing.title_options == ["The Ninth Bell"]

    orch = next(e for e in events if e["type"] == "orchestrator")
    assert orch["agents_completed"] == 4
    assert "The Ninth Ring" in result.summary


def test_producer_drops_failed_agent(monkeypatch):
    class _PartialSarvam(_FakeSarvam):
        async def structured(self, system, prompt, schema, **kw):
            if schema is MarketingPlan:
                raise RuntimeError("sarvam 500")
            return await super().structured(system, prompt, schema, **kw)

    monkeypatch.setattr(lens, "get_sarvam_llm", lambda: _PartialSarvam())
    monkeypatch.setattr(lens, "synth_voice", _fake_synth_voice)
    monkeypatch.setattr(lens, "save_simulation", lambda *a, **k: None)

    events: list[dict] = []
    result = asyncio.run(run_producer(STORY, emit=events.append))

    assert result.marketing is None
    assert result.agents_completed == 3
    errors = [e for e in events if e["type"] == "agent_error"]
    assert any(e["id"] == "marketing" for e in errors)


def test_producer_tolerates_per_character_tts_failure(monkeypatch):
    _patch(monkeypatch)

    async def flaky(text, *, voice, language_code):
        if voice == "ritu":
            raise RuntimeError("tts 429")
        return "AUDIO", "audio/wav"

    monkeypatch.setattr(lens, "synth_voice", flaky)
    result = asyncio.run(run_producer(STORY, language_code="hi-IN"))

    # One voice failed (empty audio); the other rendered; the run still completes.
    assert result.agents_completed == 4
    assert result.voices_rendered == 1
    assert result.casting.characters[0].audio_base64 == ""  # ritu failed


def test_producer_default_emit_is_noop(monkeypatch):
    _patch(monkeypatch)
    result = asyncio.run(run_producer(STORY))
    assert result.agents_completed == 4
    assert result.show_title == "The Ninth Ring"
