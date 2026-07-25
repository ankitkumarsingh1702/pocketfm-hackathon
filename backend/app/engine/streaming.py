"""Turn a callback-emitting coroutine into an NDJSON event stream.

Shared by the streaming lenses that aren't naturally async generators (the
cliffhanger planner, the showrunner agent, the MDP optimizer). The driven
coroutine receives an ``emit(event: dict)`` callback and returns a final result
dict; this helper yields each emitted event as NDJSON, then a terminal ``done``
(or ``error``) line — never raising mid-stream.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable


async def ndjson_events(
    run: Callable[[Callable[[dict], None]], Awaitable[dict]],
) -> AsyncIterator[bytes]:
    """Yield NDJSON bytes for events emitted by ``run(emit)`` + a terminal line."""
    queue: asyncio.Queue = asyncio.Queue()

    def emit(event: dict) -> None:
        queue.put_nowait(event)

    async def _runner() -> None:
        try:
            result = await run(emit)
            queue.put_nowait({"type": "done", "result": result})
        except Exception as exc:  # noqa: BLE001 - report as a terminal event, never 500
            queue.put_nowait({"type": "error", "error": str(exc)})
        finally:
            queue.put_nowait(None)  # sentinel

    task = asyncio.ensure_future(_runner())
    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield (json.dumps(event) + "\n").encode("utf-8")
    finally:
        await task
