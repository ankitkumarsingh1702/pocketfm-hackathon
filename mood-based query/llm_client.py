"""
Mood-First Search — LLM clients.

Three call sites need a model: the parser (§8.2 stage 1), the reranker (stage
4), and the persona judge (§10). All three take an `LLMClient`, so this is the
only file that knows how we authenticate.

VERTEX / ADC IS THE DEFAULT HERE
--------------------------------
The project has Application Default Credentials on GCP, so there is no API key
to manage and nothing to paste into a .env that later leaks into a commit.
`AnthropicVertex` picks ADC up automatically -- no credential handling in our
code at all, which is the main reason to prefer it.

Resolution order, first that works wins:
  1. Vertex via ADC        (GOOGLE_CLOUD_PROJECT set, or ADC has a quota project)
  2. Anthropic direct API  (ANTHROPIC_API_KEY set)
  3. None                  -> every call site falls back to its heuristic

`probe()` exists because of a specific failure mode: all three call sites
swallow exceptions and degrade silently, which is correct for demo day and
terrible for finding out that auth is broken. Run `python3 llm_client.py`
before the demo -- it makes one real round trip and tells you the truth.
"""

from __future__ import annotations

import os
from typing import Optional, Protocol

DEFAULT_MODEL = os.environ.get("MOOD_MODEL", "claude-sonnet-4-6")
DEFAULT_REGION = os.environ.get("GOOGLE_CLOUD_REGION", "us-east5")


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


def _text(msg) -> str:
    return "".join(b.text for b in msg.content if b.type == "text")


class VertexClient:
    """Claude on Vertex AI via ADC.

    Model IDs on Vertex differ from the public API -- they carry an @-suffixed
    version and are region-pinned. If a call 404s, the model is almost always
    not enabled in that region rather than misnamed; check the region before
    the model string.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        region: str = DEFAULT_REGION,
        project: Optional[str] = None,
        max_tokens: int = 2000,
    ) -> None:
        from anthropic import AnthropicVertex

        self._client = AnthropicVertex(
            region=region,
            project_id=project or os.environ.get("GOOGLE_CLOUD_PROJECT"),
        )
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, system: str, user: str) -> str:
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return _text(msg)


class DirectClient:
    """Public Anthropic API. Fallback when Vertex is not configured."""

    def __init__(self, model: str = DEFAULT_MODEL, max_tokens: int = 2000) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, system: str, user: str) -> str:
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return _text(msg)


def default_client(max_tokens: int = 2000) -> Optional[LLMClient]:
    """Never raises. A missing model degrades quality; it must not take the
    service down."""
    try:
        import google.auth

        creds, project = google.auth.default()
        project = os.environ.get("GOOGLE_CLOUD_PROJECT") or project
        if project:
            return VertexClient(project=project, max_tokens=max_tokens)
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
        out = client.complete(
            "Reply with exactly the word: ok", "ping"
        )
        return True, f"{type(client).__name__} responded: {out.strip()[:40]}"
    except Exception as exc:
        return False, f"{type(client).__name__} failed: {type(exc).__name__}: {exc}"


if __name__ == "__main__":
    ok, detail = probe()
    print(("PASS  " if ok else "FAIL  ") + detail)
    if ok:
        print("\nchecking the three call sites return valid structures:")

        from evaluate import LLMPersonaJudge  # noqa: F401
        from parser import MoodParser
        from rerank import LLMReranker  # noqa: F401

        client = default_client()
        q = MoodParser(client).parse(
            "something that feels like a rainy Sunday after heartbreak"
        )
        print(f"  parser -> destination={q.destination} "
              f"felt={q.felt_state} sparsity={q.sparsity_score:.2f} "
              f"distress={q.distress_flag}")
        print("  if destination is not None above, the model over-committed on an "
              "ambiguous query — tighten the prompt, that is the whole 3-shelf premise")
