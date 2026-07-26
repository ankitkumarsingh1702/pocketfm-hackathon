"""Gemini-on-Vertex implementation of the :class:`LLMClient` protocol.

Uses the ``google-genai`` SDK in Vertex AI mode. Structured output is
requested natively via ``response_schema`` + ``response_mime_type`` so the
model returns JSON that maps straight onto the caller's Pydantic model.
"""

from __future__ import annotations

import base64
import json
import logging

from google import genai
from google.genai import types

from app.config import settings
from app.llm.base import ImageInput, T

logger = logging.getLogger(__name__)


class GeminiVertexClient:
    """Structured-generation client backed by Gemini on Vertex AI."""

    name: str = "gemini"

    def __init__(self) -> None:
        """Construct the SDK client lazily, tolerating construction failure.

        We attempt to build the client up front but never let a construction
        error escape ``__init__`` — the client is (re)built on first use by
        :meth:`_get_client` if needed.
        """
        self.client: genai.Client | None = None
        try:
            self.client = genai.Client(
                vertexai=True,
                project=settings.google_cloud_project,
                location=settings.vertex_location,
            )
        except Exception:  # pragma: no cover - defer to lazy construction
            self.client = None

    def _get_client(self) -> genai.Client:
        """Return the SDK client, constructing it on demand if necessary."""
        if self.client is None:
            self.client = genai.Client(
                vertexai=True,
                project=settings.google_cloud_project,
                location=settings.vertex_location,
            )
        return self.client

    async def structured(
        self,
        system: str,
        prompt: str,
        schema: type[T],
        temperature: float | None = None,
        model: str | None = None,
        images: list[ImageInput] | None = None,
    ) -> T:
        """Generate JSON matching ``schema`` and return a validated instance."""
        client = self._get_client()
        model_id = model or settings.gemini_model

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=(
                temperature if temperature is not None else settings.temperature
            ),
            response_mime_type="application/json",
            response_schema=schema,
            max_output_tokens=settings.max_output_tokens,
        )
        # Gemini 2.5 models consume output tokens on internal "thinking". For the
        # fast, high-volume flash path we disable thinking so the whole token
        # budget goes to the JSON; pro keeps (bounded) thinking for quality.
        if "flash" in model_id:
            config.thinking_config = types.ThinkingConfig(thinking_budget=0)

        # Build the request contents. Text-only requests pass the bare prompt
        # string (unchanged behaviour); multimodal requests build a parts list
        # of the text plus each decoded image, so the model actually *sees* the
        # posted picture. response_schema still applies alongside image parts.
        contents: object = prompt
        if images:
            parts = [types.Part.from_text(text=prompt)]
            for img in images:
                try:
                    raw = base64.b64decode(img.data)
                except Exception:  # noqa: BLE001 - skip an undecodable image, keep the text
                    logger.warning("Skipping undecodable image part (mime=%s)", img.mime_type)
                    continue
                parts.append(types.Part.from_bytes(data=raw, mime_type=img.mime_type))
            contents = parts

        resp = await client.aio.models.generate_content(
            model=model_id,
            contents=contents,
            config=config,
        )
        obj = resp.parsed
        if isinstance(obj, schema):
            return obj
        return schema.model_validate(json.loads(resp.text or ""))
