"""LLM client interface.

The whole engine talks to exactly one method: `structured()`. It takes a
system instruction, a user prompt, and a Pydantic model, and returns a
validated instance of that model. Both the Gemini-on-Vertex and
Claude-on-Vertex implementations satisfy this Protocol, so lenses/engine code
is provider-agnostic.
"""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class LLMClient(Protocol):
    """Provider-agnostic structured-generation client."""

    name: str

    async def structured(
        self,
        system: str,
        prompt: str,
        schema: type[T],
        temperature: float | None = None,
        model: str | None = None,
    ) -> T:
        """Return a validated `schema` instance produced from `system`+`prompt`."""
        ...
