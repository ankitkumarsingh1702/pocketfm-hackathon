"""Sarvam client tests — no network.

Covers the two things that would silently break the AI Producer: the JSON
extract + one-shot repair retry in ``SarvamLLM.structured`` (Sarvam returns
OpenAI-style ``choices[0].message.content``), the base64-WAV passthrough of
``synth_voice``, and the clear error when the API key is missing.
"""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from app.config import settings
from app.llm import sarvam
from app.llm.sarvam import SarvamError, SarvamLLM, synth_voice


class _Tiny(BaseModel):
    a: int
    b: str = ""


def _chat_payload(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def _install_client(monkeypatch, responses: list[tuple[int, dict]]):
    """Patch httpx.AsyncClient with a fake returning ``responses`` in order.

    Returns a ``calls`` dict recording each POST for assertions.
    """
    calls: dict = {"n": 0, "posts": []}

    class _Resp:
        def __init__(self, code: int, payload: dict) -> None:
            self.status_code = code
            self._payload = payload
            self.text = json.dumps(payload)

        def json(self) -> dict:
            return self._payload

    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, json=None):
            calls["posts"].append({"url": url, "json": json, "headers": headers})
            code, payload = responses[min(calls["n"], len(responses) - 1)]
            calls["n"] += 1
            return _Resp(code, payload)

    monkeypatch.setattr(sarvam.httpx, "AsyncClient", _Client)
    return calls


async def test_structured_parses_valid_json(monkeypatch):
    monkeypatch.setattr(settings, "sarvam_api_key", "sk_test")
    calls = _install_client(monkeypatch, [(200, _chat_payload('{"a": 7, "b": "ok"}'))])

    out = await SarvamLLM().structured(system="sys", prompt="p", schema=_Tiny)

    assert out.a == 7 and out.b == "ok"
    assert calls["n"] == 1
    # Auth header + JSON mode are set as Sarvam requires.
    assert calls["posts"][0]["headers"]["api-subscription-key"] == "sk_test"
    assert calls["posts"][0]["json"]["response_format"] == {"type": "json_object"}


async def test_structured_repairs_once_on_bad_json(monkeypatch):
    monkeypatch.setattr(settings, "sarvam_api_key", "sk_test")
    calls = _install_client(
        monkeypatch,
        [
            (200, _chat_payload('{"a": "not-an-int"}')),   # fails validation
            (200, _chat_payload('{"a": 5}')),               # repair succeeds
        ],
    )

    out = await SarvamLLM().structured(system="sys", prompt="p", schema=_Tiny)

    assert out.a == 5
    assert calls["n"] == 2  # one repair round-trip
    # The repair turn re-sends the conversation with the assistant's bad reply.
    assert any(m["role"] == "assistant" for m in calls["posts"][1]["json"]["messages"])


async def test_structured_extracts_object_from_prose(monkeypatch):
    monkeypatch.setattr(settings, "sarvam_api_key", "sk_test")
    _install_client(monkeypatch, [(200, _chat_payload('Here you go:\n```json\n{"a": 3}\n```'))])

    out = await SarvamLLM().structured(system="sys", prompt="p", schema=_Tiny)
    assert out.a == 3


async def test_structured_raises_on_http_error(monkeypatch):
    monkeypatch.setattr(settings, "sarvam_api_key", "sk_test")
    _install_client(monkeypatch, [(500, {"error": "boom"})])

    with pytest.raises(SarvamError):
        await SarvamLLM().structured(system="s", prompt="p", schema=_Tiny)


async def test_synth_voice_returns_base64_wav(monkeypatch):
    monkeypatch.setattr(settings, "sarvam_api_key", "sk_test")
    calls = _install_client(monkeypatch, [(200, {"audios": ["QUJD"]})])

    audio_b64, mime = await synth_voice("Namaste", voice="ritu", language_code="hi-IN")

    assert audio_b64 == "QUJD" and mime == "audio/wav"
    body = calls["posts"][0]["json"]
    assert body["speaker"] == "ritu" and body["target_language_code"] == "hi-IN"
    assert body["model"] == settings.sarvam_tts_model


async def test_synth_voice_empty_text_skips_call(monkeypatch):
    monkeypatch.setattr(settings, "sarvam_api_key", "sk_test")
    calls = _install_client(monkeypatch, [(200, {"audios": ["QUJD"]})])

    audio_b64, mime = await synth_voice("   ", voice="ritu", language_code="hi-IN")
    assert audio_b64 == "" and mime == "audio/wav"
    assert calls["n"] == 0  # no network for empty input


async def test_missing_key_raises(monkeypatch):
    monkeypatch.setattr(settings, "sarvam_api_key", "")
    with pytest.raises(SarvamError):
        await SarvamLLM().structured(system="s", prompt="p", schema=_Tiny)
    with pytest.raises(SarvamError):
        await synth_voice("hi", voice="ritu", language_code="hi-IN")
