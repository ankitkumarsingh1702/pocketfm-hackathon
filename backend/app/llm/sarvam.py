"""Sarvam client for the AI Producer lens — chat LLM + voice-casting TTS.

The AI Producer runs end-to-end on Sarvam:

* :meth:`SarvamLLM.structured` satisfies the same :class:`~app.llm.base.LLMClient`
  protocol the rest of the engine uses, so the producer's four sub-agents are
  written exactly like every other lens. Sarvam's chat-completions API is
  OpenAI-compatible; we request ``response_format={"type": "json_object"}``
  (guaranteed-valid JSON), inject the target schema into the system prompt,
  validate with Pydantic, and repair once on a parse/validation miss. Sarvam's
  reasoning mode is disabled per call so the token budget yields the JSON answer
  rather than internal thinking (Sarvam counts reasoning tokens against tokens).
* :func:`synth_voice` calls Sarvam TTS (``bulbul:v3``) so casting is *audible* —
  one short sample line per character in its assigned voice, returned as base64 WAV.

The API key is read from ``settings.sarvam_api_key`` (env / Secret Manager); it is
never hardcoded or logged. Both endpoints authenticate with the
``api-subscription-key`` header. All network access uses ``httpx`` with a bounded
timeout.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache

import httpx
from pydantic import ValidationError

from app.config import settings
from app.llm.base import ImageInput, T

logger = logging.getLogger(__name__)


class SarvamError(RuntimeError):
    """Raised when a Sarvam API call fails or the API key is missing."""


def _require_key() -> str:
    """Return the configured Sarvam key, or raise a clear, actionable error."""
    key = (settings.sarvam_api_key or "").strip()
    if not key:
        raise SarvamError(
            "SARVAM_API_KEY is not set. Add it to backend/.env (local) or Secret "
            "Manager (deployed) to enable the AI Producer."
        )
    return key


def _extract_json_object(text: str) -> str:
    """Return the first balanced top-level ``{...}`` block from ``text``.

    ``json_object`` mode already yields valid JSON, but models occasionally wrap it
    in prose or a ```json fence; this pulls the object out so validation still
    passes. Raises ``ValueError`` when no balanced object is present.
    """
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in response")
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError("unbalanced JSON object in response")


class SarvamLLM:
    """Structured-generation client backed by Sarvam's chat-completions API."""

    name: str = "sarvam"

    def __init__(self) -> None:
        self._base = settings.sarvam_api_base_url.rstrip("/")

    async def _chat(
        self,
        messages: list[dict],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """POST one chat-completions request and return the assistant text."""
        key = _require_key()
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            # Guaranteed-valid JSON; we still validate against the schema below.
            "response_format": {"type": "json_object"},
            # Disable reasoning so the whole token budget yields the JSON answer.
            "reasoning_effort": None,
        }
        async with httpx.AsyncClient(timeout=settings.sarvam_timeout_seconds) as client:
            resp = await client.post(
                f"{self._base}/v1/chat/completions",
                headers={
                    "api-subscription-key": key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if resp.status_code >= 400:
            raise SarvamError(f"Sarvam chat {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise SarvamError(f"Sarvam chat: unexpected response shape ({e})")

    async def structured(
        self,
        system: str,
        prompt: str,
        schema: type[T],
        temperature: float | None = None,
        model: str | None = None,
        images: list[ImageInput] | None = None,  # accepted for protocol parity; unused
    ) -> T:
        """Generate JSON matching ``schema`` and return a validated instance.

        One repair pass: on a parse/validation miss the model is handed its own
        output plus the error and asked to correct it, then re-validated. A second
        failure propagates so the caller (a producer sub-agent) is dropped like any
        other failed agent.
        """
        model_id = model or settings.sarvam_llm_model
        temp = temperature if temperature is not None else settings.sarvam_temperature
        schema_json = json.dumps(schema.model_json_schema())
        sys = (
            f"{system}\n\nYou MUST reply with a single JSON object only — no prose, "
            f"no markdown fences. It MUST validate against this JSON schema:\n{schema_json}"
        )
        messages = [
            {"role": "system", "content": sys},
            {"role": "user", "content": prompt},
        ]
        raw = await self._chat(
            messages, model=model_id, temperature=temp, max_tokens=settings.sarvam_max_tokens
        )
        try:
            return schema.model_validate_json(_extract_json_object(raw))
        except (ValidationError, ValueError) as first_err:
            repair = messages + [
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": (
                        f"That did not validate against the schema ({first_err}). "
                        "Reply again with ONLY the corrected JSON object."
                    ),
                },
            ]
            raw2 = await self._chat(
                repair, model=model_id, temperature=0.1, max_tokens=settings.sarvam_max_tokens
            )
            return schema.model_validate_json(_extract_json_object(raw2))


async def synth_voice(text: str, *, voice: str, language_code: str) -> tuple[str, str]:
    """Render ``text`` in a Sarvam ``bulbul:v3`` voice; return ``(audio_base64, mime)``.

    Used by the Voice Casting Director to voice a short sample line per character.
    Sarvam already returns base64 WAV, so the string is passed straight through to
    the browser ``<audio>`` element (no decode/re-encode). Empty input yields an
    empty clip rather than an error, so one silent character never fails the run.
    """
    key = _require_key()
    text = (text or "").strip()[: settings.sarvam_tts_max_chars]
    if not text:
        return "", "audio/wav"
    payload = {
        "text": text,
        "target_language_code": language_code,
        "model": settings.sarvam_tts_model,
        "speaker": voice,
        "output_audio_codec": settings.sarvam_tts_codec,
    }
    base = settings.sarvam_api_base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=settings.sarvam_timeout_seconds) as client:
        resp = await client.post(
            f"{base}/text-to-speech",
            headers={"api-subscription-key": key, "Content-Type": "application/json"},
            json=payload,
        )
    if resp.status_code >= 400:
        raise SarvamError(f"Sarvam TTS {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    audios = data.get("audios") or []
    if not audios:
        raise SarvamError("Sarvam TTS returned no audio")
    return audios[0], "audio/wav"


@lru_cache(maxsize=1)
def get_sarvam_llm() -> SarvamLLM:
    """Return the Sarvam chat client as a cached per-process singleton."""
    return SarvamLLM()
