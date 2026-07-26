"""Narration lens + TTS tests — no paid model calls.

Covers the two things that would silently break the feature: the WAV header that
makes Gemini's raw PCM playable, the Gemini->Chirp fallback + failure latch, and
the text-hash cache that keeps repeat demos quota-free.
"""

from __future__ import annotations

import base64

from app.config import settings
from app.lenses import narrate
from app.llm import tts


def test_pcm_to_wav_has_riff_header():
    pcm = b"\x00\x01" * 1000  # 1000 signed-16-bit samples
    wav = tts.pcm_to_wav(pcm)
    assert wav[:4] == b"RIFF"
    assert wav[8:12] == b"WAVE"
    assert len(wav) == 44 + len(pcm)  # 44-byte header + payload


def test_chirp_voice_id_derives_from_bare_name():
    assert tts._chirp_voice_id("Charon") == "en-US-Chirp3-HD-Charon"
    # Already-qualified ids pass through unchanged.
    assert tts._chirp_voice_id("en-US-Chirp3-HD-Fenrir") == "en-US-Chirp3-HD-Fenrir"


async def test_synth_falls_back_to_chirp_when_gemini_fails(monkeypatch):
    async def boom(text, voice, style):
        raise RuntimeError("preview model not enabled on this project")

    async def fake_chirp(text, voice, rate):
        return tts.SynthResult(audio=b"MP3", mime="audio/mp3", voice=voice, engine="chirp")

    monkeypatch.setattr(tts, "_gemini_tts_ok", None, raising=False)
    monkeypatch.setattr(settings, "tts_engine", "auto")
    monkeypatch.setattr(tts, "_synth_gemini", boom)
    monkeypatch.setattr(tts, "_synth_chirp", fake_chirp)

    result = await tts.synth("hello", voice="Charon", rate=1.0, gemini_style="say it")
    assert result.engine == "chirp"
    # The failure latches so we stop retrying a model this project can't reach.
    assert tts._gemini_tts_ok is False


async def test_run_narration_caches_by_text(monkeypatch, tmp_path):
    calls = {"n": 0}

    async def fake_synth(text, *, voice, rate, gemini_style):
        calls["n"] += 1
        return tts.SynthResult(
            audio=b"AUDIO-" + text.encode()[:6], mime="audio/mp3", voice=voice, engine="chirp"
        )

    monkeypatch.setattr(settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(tts, "synth", fake_synth)

    first = await narrate.run_narration("weak ending", "strong cliffhanger")
    assert calls["n"] == 2  # one synth per clip on the first run
    assert first.original.style == "flat"
    assert first.optimized.style == "dramatic"
    base64.b64decode(first.original.audio_base64)  # round-trips

    second = await narrate.run_narration("weak ending", "strong cliffhanger")
    assert calls["n"] == 2  # both served from cache — no new synthesis
    assert second.optimized.audio_base64 == first.optimized.audio_base64


async def test_run_narration_handles_empty_text(monkeypatch, tmp_path):
    async def fake_synth(text, *, voice, rate, gemini_style):
        return tts.SynthResult(audio=b"X", mime="audio/mp3", voice=voice, engine="chirp")

    monkeypatch.setattr(settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(tts, "synth", fake_synth)

    result = await narrate.run_narration("", "a real cliffhanger")
    assert result.original.audio_base64 == ""  # silent placeholder, no crash
    assert result.optimized.audio_base64 != ""
