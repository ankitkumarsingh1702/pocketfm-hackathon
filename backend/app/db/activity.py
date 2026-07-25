"""Best-effort in-process activity log for knowledge-graph reads/writes.

Purely observational: every read from / write to the Neo4j canon graph is
recorded into a small ring buffer so the frontend "DB / Memory" tab can show,
live, that the agents genuinely read shared memory and write their verdicts
back. Mirrors the best-effort contract of :mod:`app.db.firestore` — recording
never raises and never affects engine behaviour.

The buffer is process-local (a module-level ``deque``), which is exactly right
for a single Cloud Run instance / live demo. If cross-instance durability is
ever needed, ``record_activity`` can additionally best-effort write to Firestore
using the same client pattern as :mod:`app.db.firestore`.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from itertools import count

from app.config import settings

logger = logging.getLogger(__name__)

# Module-level ring buffer, sized from settings at import time. maxlen bounds
# memory so a long-running instance can never grow this without limit.
_events: deque[dict] = deque(maxlen=max(1, settings.activity_log_max))
_seq = count(1)


def record_activity(
    op: str,
    fn: str,
    source: str = "",
    detail: str = "",
    counts: dict | None = None,
) -> None:
    """Append one graph read/write event. Best-effort; never raises.

    ``op`` is ``'read'`` | ``'write'`` | ``'skipped'``; ``fn`` the store
    function that ran; ``source`` the agent/lens that triggered it; ``detail`` a
    human-readable sentence for the UI; ``counts`` any numeric payload
    (nodes/edges/segments) worth surfacing.
    """
    if not settings.use_activity_log:
        return
    try:
        _events.append(
            {
                "seq": next(_seq),
                "ts": time.time(),
                "op": op,
                "fn": fn,
                "source": source or "unknown",
                "detail": detail,
                "counts": counts or {},
            }
        )
    except Exception as exc:  # noqa: BLE001 - observability must never break a run
        logger.warning("record_activity failed: %s", exc)


def get_recent_activity(limit: int = 50) -> list[dict]:
    """Return up to ``limit`` most-recent events, oldest-first (newest last)."""
    if limit <= 0:
        return []
    return list(_events)[-limit:]


def clear_activity() -> None:
    """Drop all recorded events. Used by tests."""
    _events.clear()
