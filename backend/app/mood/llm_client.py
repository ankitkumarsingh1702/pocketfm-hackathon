"""
Mood-First Search — LLM clients.

Three call sites need a model: the parser (§8.2 stage 1), the reranker (stage
4), and the persona judge (§10). All three take an ``LLMClient`` and call one
synchronous method — ``complete(system, user) -> str`` — then parse the JSON out
of the text themselves. So this is the only file that knows how we authenticate.

REUSES THE STUDIO'S VERTEX CONFIG
---------------------------------
The rest of the backend already talks to Vertex AI via ``app.config.settings``
(project, region, provider, model) using Application Default Credentials. This
module reuses exactly those settings and the same ADC auth, so the mood feature
authenticates identically to every other lens — there is no second credential
path to manage.

It does NOT route through ``app.llm.get_llm()``: that client is async and
structured-output only (it always forces a Pydantic schema), whereas these three
call sites are synchronous and want raw text they can parse defensively. So we
build a thin *synchronous* text client over the same SDKs instead.

Resolution order, first that works wins:
  1. Provider from ``settings.llm_provider``:
       "gemini" -> Gemini on Vertex (google-genai, sync)
       anything else ("claude") -> Claude on Vertex (anthropic, sync)
  2. Anthropic direct API  (ANTHROPIC_API_KEY set) — fallback when Vertex init fails
  3. None                  -> every call site falls back to its heuristic

``probe()`` exists because all three call sites swallow exceptions and degrade
silently, which is correct for demo day and terrible for finding out that auth
is broken. Run ``python -m app.mood.llm_client`` before the demo — it makes one
real round trip and tells the truth.
"""

from __future__ import annotations

import os
from typing import Optional, Protocol

from app.config import settings

# Kept overridable by env for quick experiments, but the defaults come from the
# shared studio settings so mood and the other lenses stay on the same models.
DEFAULT_MAX_TOKENS = 2000


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


def _anthropic_text(msg) -> str:
    return "".join(
        getattr(b, "text", "") for b in msg.content
        if getattr(b, "type", "") == "text"
    )


class GeminiClient:
    """Gemini on Vertex AI via ADC — synchronous, free-form text.

    Uses the ``google-genai`` SDK's blocking ``client.models`` surface (the same
    SDK the studio's async Gemini lens uses via ``client.aio.models``). We ask
    for plain text, not a ``response_schema``, because the mood call sites parse
    the JSON themselves and want to keep their defensive fallbacks.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        project: Optional[str] = None,
        location: Optional[str] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        from google import genai

        self._genai = genai
        self._client = genai.Client(
            vertexai=True,
            project=project or settings.google_cloud_project,
            location=location or settings.vertex_location,
        )
        self._model = model or settings.gemini_model
        self._max_tokens = max_tokens

    def complete(self, system: str, user: str) -> str:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.4,
            max_output_tokens=self._max_tokens,
        )
        # Flash spends output tokens on internal "thinking"; the mood prompts are
        # short and want the whole budget on the answer.
        if "flash" in self._model:
            config.thinking_config = types.ThinkingConfig(thinking_budget=0)
        resp = self._client.models.generate_content(
            model=self._model, contents=user, config=config,
        )
        return resp.text or ""


class VertexClient:
    """Claude on Vertex AI via ADC — synchronous.

    Model IDs on Vertex are region-pinned. If a call 404s, the model is almost
    always not enabled in that region rather than misnamed; check the region
    (``settings.claude_location``) before the model string.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        region: Optional[str] = None,
        project: Optional[str] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        from anthropic import AnthropicVertex

        self._client = AnthropicVertex(
            region=region or settings.claude_location,
            project_id=project or settings.google_cloud_project,
        )
        self._model = model or settings.claude_model
        self._max_tokens = max_tokens

    def complete(self, system: str, user: str) -> str:
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return _anthropic_text(msg)


class DirectClient:
    """Public Anthropic API. Fallback when Vertex is not configured."""

    def __init__(self, model: Optional[str] = None, max_tokens: int = DEFAULT_MAX_TOKENS) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self._model = model or settings.claude_model
        self._max_tokens = max_tokens

    def complete(self, system: str, user: str) -> str:
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return _anthropic_text(msg)


def default_client(max_tokens: int = DEFAULT_MAX_TOKENS) -> Optional[LLMClient]:
    """Never raises. A missing model degrades quality; it must not take the
    service down, so every construction path that fails falls through to the
    next, and the last resort is ``None`` (pure heuristics)."""
    provider = (settings.llm_provider or "").lower()

    if provider == "gemini":
        try:
            return GeminiClient(max_tokens=max_tokens)
        except Exception:
            pass
    else:
        try:
            return VertexClient(max_tokens=max_tokens)
        except Exception:
            pass

    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return DirectClient(max_tokens=max_tokens)
        except Exception:
            pass
    return None


def probe() -> tuple[bool, str]:
    """One real round trip. Run this before the demo."""
    client = default_client(max_tokens=64)
    if client is None:
        return False, "no client resolved — parser/reranker/judge are all on heuristics"
    try:
        out = client.complete("Reply with exactly the word: ok", "ping")
        return True, f"{type(client).__name__} responded: {out.strip()[:40]}"
    except Exception as exc:
        return False, f"{type(client).__name__} failed: {type(exc).__name__}: {exc}"


if __name__ == "__main__":
    ok, detail = probe()
    print(("PASS  " if ok else "FAIL  ") + detail)
    if ok:
        print("\nchecking the three call sites return valid structures:")

        from app.mood.evaluate import LLMPersonaJudge  # noqa: F401
        from app.mood.parser import MoodParser
        from app.mood.rerank import LLMReranker  # noqa: F401

        client = default_client()
        q = MoodParser(client).parse(
            "something that feels like a rainy Sunday after heartbreak"
        )
        print(f"  parser -> destination={q.destination} "
              f"felt={q.felt_state} sparsity={q.sparsity_score:.2f} "
              f"distress={q.distress_flag}")
        print("  if destination is not None above, the model over-committed on an "
              "ambiguous query — tighten the prompt, that is the whole 3-shelf premise")
