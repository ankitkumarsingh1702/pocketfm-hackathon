"""Claude-on-Vertex implementation of the :class:`LLMClient` protocol.

Uses the ``anthropic`` SDK's :class:`AsyncAnthropicVertex` client. Claude has
no native ``response_schema`` knob, so we append the target JSON schema to the
system prompt, then defensively parse the JSON out of the text response
(stripping optional Markdown code fences).
"""

from __future__ import annotations

import json

from anthropic import AsyncAnthropicVertex

from app.config import settings
from app.llm.base import T


class ClaudeVertexClient:
    """Structured-generation client backed by Claude on Vertex AI."""

    name: str = "claude"

    def __init__(self) -> None:
        """Construct the SDK client lazily, tolerating construction failure.

        We attempt to build the client up front but never let a construction
        error escape ``__init__`` — the client is (re)built on first use by
        :meth:`_get_client` if needed.
        """
        self.client: AsyncAnthropicVertex | None = None
        try:
            self.client = AsyncAnthropicVertex(
                project_id=settings.google_cloud_project,
                region=settings.claude_location,
            )
        except Exception:  # pragma: no cover - defer to lazy construction
            self.client = None

    def _get_client(self) -> AsyncAnthropicVertex:
        """Return the SDK client, constructing it on demand if necessary."""
        if self.client is None:
            self.client = AsyncAnthropicVertex(
                project_id=settings.google_cloud_project,
                region=settings.claude_location,
            )
        return self.client

    async def structured(
        self,
        system: str,
        prompt: str,
        schema: type[T],
        temperature: float | None = None,
    ) -> T:
        """Generate JSON matching ``schema`` and return a validated instance."""
        client = self._get_client()
        system2 = (
            system
            + "\n\nRespond with ONLY a JSON object matching this JSON schema "
            + "(no prose, no code fences):\n"
            + json.dumps(schema.model_json_schema())
        )
        msg = await client.messages.create(
            model=settings.claude_model,
            max_tokens=settings.max_output_tokens,
            temperature=(temperature or settings.temperature),
            system=system2,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            getattr(b, "text", "")
            for b in msg.content
            if getattr(b, "type", "") == "text"
        )

        # Strip optional ```json ... ``` fences, then isolate the JSON object
        # by taking the substring from the first '{' to the last '}'.
        cleaned = text.strip()
        if "```" in cleaned:
            cleaned = cleaned.replace("```json", "").replace("```", "").strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end >= start:
            cleaned = cleaned[start : end + 1]

        data = json.loads(cleaned)
        return schema.model_validate(data)
