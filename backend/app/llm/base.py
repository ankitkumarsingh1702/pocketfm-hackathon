"""LLM client interface.

The whole engine talks to exactly one method: `structured()`. It takes a
system instruction, a user prompt, and a Pydantic model, and returns a
validated instance of that model. Both the Gemini-on-Vertex and
Claude-on-Vertex implementations satisfy this Protocol, so lenses/engine code
is provider-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class ImageInput:
    """One image attached to a prompt, for multimodal (vision) generation.

    ``data`` is the raw base64-encoded image bytes WITHOUT any ``data:`` URI
    prefix; ``mime_type`` is an IANA image type such as ``image/png`` or
    ``image/jpeg``. Passed through to the provider as a vision content part.
    """

    data: str
    mime_type: str = "image/png"


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
        images: list[ImageInput] | None = None,
    ) -> T:
        """Return a validated `schema` instance produced from `system`+`prompt`.

        When ``images`` are supplied they are sent as vision parts alongside the
        text prompt (both Gemini-on-Vertex and Claude-on-Vertex support this).
        Text-only callers omit ``images`` and behave exactly as before.
        """
        ...
