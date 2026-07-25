"""LLM client factory.

Exposes a single cached :func:`get_llm` that returns the configured provider's
client. The result is a module-level singleton (via ``lru_cache``) so SDK
clients are constructed once per process.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import settings
from app.llm.base import LLMClient
from app.llm.claude_vertex import ClaudeVertexClient
from app.llm.gemini_vertex import GeminiVertexClient


@lru_cache(maxsize=1)
def get_llm() -> LLMClient:
    """Return the configured LLM client as a cached singleton.

    Picks by :data:`settings.llm_provider`: ``"gemini"`` -> Gemini on Vertex,
    anything else -> Claude on Vertex.
    """
    if settings.llm_provider == "gemini":
        return GeminiVertexClient()
    return ClaudeVertexClient()
