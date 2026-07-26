"""Text-to-speech narration for the Cliffhanger Optimizer's "hear the difference".

Turns a scene into narrated audio so the hook-score lift is *audible*: the weak
original read flat and passive, the optimized cliffhanger read with dramatic,
in-character tension.

Reliability-first for a live demo:

* PRIMARY — Google Cloud Text-to-Speech **Chirp 3 HD** (GA, ADC-authenticated,
  region-stable). Returns MP3 that a browser ``<audio>`` element plays directly.
* ENHANCED — **Gemini 2.5 native TTS** (preview) understands natural-language
  style direction ("read in a tense whisper"), so it lands the "character feel"
  best. It is preview + org-policy-gated on some projects, so we try it first
  only when ``settings.tts_engine`` allows, and we ALWAYS fall back to Chirp on
  any error. The first failure latches a process-wide flag so we stop retrying a
  model this project can't reach.

``synth()`` never leaks a Gemini-specific failure to the caller: it degrades
Gemini -> Chirp transparently and returns a provider-agnostic ``SynthResult``.
"""

from __future__ import annotations

import asyncio
import io
import logging
import wave
from dataclasses import dataclass

from app.config import settings

logger = logging.getLogger(__name__)

# Gemini native TTS emits headerless PCM: signed 16-bit little-endian, mono, 24kHz.
_GEMINI_PCM_RATE = 24000
_GEMINI_PCM_WIDTH = 2  # bytes per sample (16-bit)
_GEMINI_PCM_CHANNELS = 1

# Tri-state: None = not yet tried, True = reachable, False = gave up (use Chirp).
_gemini_tts_ok: bool | None = None

# Lazily built SDK clients (constructed on first use, like GeminiVertexClient).
_chirp_client = None
_genai_client = None


@dataclass(frozen=True)
class SynthResult:
    """One synthesized clip, ready to base64-encode for the browser.

    ``audio`` is a self-contained container (MP3 from Chirp, WAV from Gemini) so
    the client needs no decoding — just a blob/data URL fed to ``<audio>``.
    """

    audio: bytes
    mime: str          # "audio/mp3" (Chirp) | "audio/wav" (Gemini)
    voice: str
    engine: str        # "chirp" | "gemini"


def pcm_to_wav(
    pcm: bytes,
    *,
    rate: int = _GEMINI_PCM_RATE,
    width: int = _GEMINI_PCM_WIDTH,
    channels: int = _GEMINI_PCM_CHANNELS,
) -> bytes:
    """Wrap raw little-endian PCM samples in a WAV/RIFF container.

    Gemini TTS returns headerless L16 PCM, which a browser ``<audio>`` element
    cannot play; wrapping it in a WAV header makes it playable with zero
    client-side decoding. Chirp already returns MP3, so this is Gemini-only.
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _chirp_voice_id(voice: str) -> str:
    """Map a bare voice name (shared Gemini/Chirp set) to a Chirp 3 HD voice id.

    e.g. ``"Charon"`` -> ``"en-US-Chirp3-HD-Charon"``. If the caller already
    passed a fully-qualified id, use it as-is.
    """
    if "Chirp3-HD" in voice:
        return voice
    return f"{settings.tts_language_code}-Chirp3-HD-{voice}"


def _get_chirp_client():
    global _chirp_client
    if _chirp_client is None:
        from google.cloud import texttospeech

        _chirp_client = texttospeech.TextToSpeechClient()
    return _chirp_client


def _synth_chirp_sync(text: str, voice: str, rate: float) -> bytes:
    """Blocking Chirp synthesis (called via ``asyncio.to_thread``)."""
    from google.cloud import texttospeech

    try:
        from google.api_core.exceptions import InvalidArgument
    except Exception:  # pragma: no cover - defensive
        InvalidArgument = Exception  # type: ignore[assignment]

    client = _get_chirp_client()
    voice_id = _chirp_voice_id(voice)

    def _call(audio_config) -> bytes:
        resp = client.synthesize_speech(
            input=texttospeech.SynthesisInput(text=text),
            voice=texttospeech.VoiceSelectionParams(
                language_code=settings.tts_language_code, name=voice_id
            ),
            audio_config=audio_config,
        )
        return resp.audio_content

    try:
        return _call(
            texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3, speaking_rate=rate
            )
        )
    except InvalidArgument:
        # Some voices reject speaking_rate — retry at default pacing rather than
        # failing the whole clip.
        return _call(texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3))


async def _synth_chirp(text: str, voice: str, rate: float) -> SynthResult:
    audio = await asyncio.to_thread(_synth_chirp_sync, text, voice, rate)
    return SynthResult(audio=audio, mime="audio/mp3", voice=_chirp_voice_id(voice), engine="chirp")


def _get_genai_client():
    global _genai_client
    if _genai_client is None:
        from google import genai

        _genai_client = genai.Client(
            vertexai=True,
            project=settings.google_cloud_project,
            location=settings.tts_location,
        )
    return _genai_client


async def _synth_gemini(text: str, voice: str, style_instruction: str) -> SynthResult:
    from google.genai import types

    client = _get_genai_client()
    resp = await client.aio.models.generate_content(
        model=settings.tts_model,
        contents=f"{style_instruction}\n\n{text}",
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                )
            ),
        ),
    )
    try:
        pcm = resp.candidates[0].content.parts[0].inline_data.data
    except (AttributeError, IndexError, TypeError) as e:
        # Gemini TTS occasionally returns text tokens instead of audio (a known
        # preview quirk); treat as a failure so we fall back to Chirp.
        raise RuntimeError(f"Gemini TTS returned no audio part: {e}") from e
    if not pcm:
        raise RuntimeError("Gemini TTS returned an empty audio part")
    return SynthResult(audio=pcm_to_wav(pcm), mime="audio/wav", voice=voice, engine="gemini")


def _should_try_gemini() -> bool:
    """True when Gemini TTS is allowed and hasn't already failed this process."""
    return settings.tts_engine != "chirp" and _gemini_tts_ok is not False


def _mark_gemini_up() -> None:
    global _gemini_tts_ok
    if _gemini_tts_ok is None:
        _gemini_tts_ok = True


def _mark_gemini_down(err: Exception) -> None:
    global _gemini_tts_ok
    _gemini_tts_ok = False
    logger.warning("Gemini TTS unavailable; using Chirp fallback. %s", err)


async def synth(text: str, *, voice: str, rate: float, gemini_style: str) -> SynthResult:
    """Synthesize one clip, preferring Gemini's expressive delivery when reachable.

    ``voice`` is the bare shared voice name (e.g. "Charon"); Chirp derives its
    full voice id from it. ``rate`` steers Chirp pacing; ``gemini_style`` is the
    natural-language delivery direction handed to Gemini. On any Gemini error we
    transparently fall back to Chirp so a Play never fails for the user.
    """
    text = (text or "").strip()[: settings.tts_max_chars]
    if _should_try_gemini():
        try:
            result = await _synth_gemini(text, voice, gemini_style)
            _mark_gemini_up()
            return result
        except Exception as e:  # noqa: BLE001 - degrade to the reliable engine
            _mark_gemini_down(e)
    return await _synth_chirp(text, voice, rate)
