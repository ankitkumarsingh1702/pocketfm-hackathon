"""Best-effort activity log for knowledge-graph reads/writes.

Records every read from / write to the Neo4j canon graph so the "DB / Memory"
tab can show, live, that agents genuinely read shared memory and write their
verdicts back. Two layers, both best-effort (recording never raises and never
affects engine behaviour):

* a fast process-local ring buffer (a module-level ``deque``), and
* durable ``(:ActivityEvent)`` nodes in Neo4j.

The durable layer is the important one: without it the counters live only in one
Cloud Run instance's memory and reset to zero on every cold start / redeploy —
which is exactly why the tab can show "0 memory reads" even though the canon
itself (persisted in Neo4j) is full. Persisting each event makes the reads/writes
an accumulating, cross-instance record of real agent memory access.

The Neo4j write is fire-and-forget (scheduled on the running event loop) so that
``record_activity`` stays synchronous and instant for its callers. Reads prefer
the durable store and fall back to the ring buffer when the graph is unavailable
or has no events yet.
"""

from __future__ import annotations

import asyncio
import json
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

# Strong refs to in-flight durable writes so they aren't garbage-collected
# mid-flight (asyncio only holds weak refs to tasks).
_bg_tasks: set[asyncio.Task] = set()


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
    (nodes/edges/segments) worth surfacing. Appends to the in-process buffer
    immediately and schedules a durable Neo4j write in the background.
    """
    if not settings.use_activity_log:
        return
    event = {
        "seq": next(_seq),
        "ts": time.time(),
        "op": op,
        "fn": fn,
        "source": source or "unknown",
        "detail": detail,
        "counts": counts or {},
    }
    try:
        _events.append(event)
    except Exception as exc:  # noqa: BLE001 - observability must never break a run
        logger.warning("record_activity (buffer) failed: %s", exc)
    _schedule_persist(event)


def _schedule_persist(event: dict) -> None:
    """Fire-and-forget the durable write, if an event loop is running.

    Called from sync code inside async request handlers, so a loop is normally
    present; in a bare sync context (some tests, CLI) there is none and we simply
    keep the in-memory record.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(_persist_event(event))
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


async def _persist_event(event: dict) -> None:
    """Write one event as an ``(:ActivityEvent)`` node. Best-effort."""
    from app.graph.driver import get_driver

    driver = get_driver()
    if driver is None:
        return
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            await session.run(
                "CREATE (a:ActivityEvent {seq:$seq, ts:$ts, op:$op, fn:$fn, "
                "source:$source, detail:$detail, counts:$counts})",
                seq=event["seq"],
                ts=event["ts"],
                op=event["op"],
                fn=event["fn"],
                source=event["source"],
                detail=event["detail"],
                counts=json.dumps(event["counts"]),
            )
    except Exception as exc:  # noqa: BLE001 - durability is strictly best-effort
        logger.warning("record_activity (durable) failed: %s", exc)


async def flush_activity() -> None:
    """Await any in-flight durable writes. Used by the seed warm-up so events
    are persisted before a short-lived script exits."""
    if _bg_tasks:
        await asyncio.gather(*list(_bg_tasks), return_exceptions=True)


def _tally(events: list[dict]) -> dict[str, int]:
    reads = sum(1 for e in events if e.get("op") == "read")
    writes = sum(1 for e in events if e.get("op") == "write")
    return {"reads": reads, "writes": writes, "total": len(events)}


def get_recent_activity(limit: int = 50) -> list[dict]:
    """Ring-buffer events, oldest-first (newest last). In-memory fallback."""
    if limit <= 0:
        return []
    return list(_events)[-limit:]


async def get_recent_activity_durable(limit: int = 50) -> tuple[list[dict], dict[str, int]]:
    """Recent events + true totals from the durable Neo4j log.

    Returns ``(events, totals)`` with events oldest-first (matching the feed
    contract) and ``totals = {"reads", "writes", "total"}`` counted across ALL
    persisted events (not just the returned page). Falls back to the in-process
    ring buffer when the graph is unavailable or has no events yet, so the tab
    always shows *something* real.
    """
    from app.graph.driver import get_driver

    driver = get_driver()
    if driver is None or limit <= 0:
        buf = get_recent_activity(limit)
        return buf, _tally(list(_events))

    try:
        events: list[dict] = []
        totals = {"reads": 0, "writes": 0, "total": 0}
        async with driver.session(database=settings.neo4j_database) as session:
            result = await session.run(
                "MATCH (a:ActivityEvent) "
                "RETURN a.seq AS seq, a.ts AS ts, a.op AS op, a.fn AS fn, "
                "a.source AS source, a.detail AS detail, a.counts AS counts "
                "ORDER BY a.ts DESC LIMIT $limit",
                limit=limit,
            )
            async for rec in result:
                try:
                    parsed = json.loads(rec["counts"]) if rec["counts"] else {}
                except Exception:  # noqa: BLE001 - tolerate a bad payload
                    parsed = {}
                events.append(
                    {
                        "seq": rec["seq"] or 0,
                        "ts": rec["ts"] or 0.0,
                        "op": rec["op"] or "read",
                        "fn": rec["fn"] or "",
                        "source": rec["source"] or "unknown",
                        "detail": rec["detail"] or "",
                        "counts": parsed,
                    }
                )
            tres = await session.run(
                "MATCH (a:ActivityEvent) RETURN a.op AS op, count(*) AS c"
            )
            async for rec in tres:
                c = int(rec["c"] or 0)
                totals["total"] += c
                if rec["op"] == "read":
                    totals["reads"] = c
                elif rec["op"] == "write":
                    totals["writes"] = c

        if not events:
            buf = get_recent_activity(limit)
            return buf, _tally(list(_events))

        events.reverse()  # newest-first (query order) -> oldest-first (contract)
        # Re-number seq per response so React keys stay unique even if two Cloud
        # Run instances both started their in-process counter at 1.
        for i, e in enumerate(events, start=1):
            e["seq"] = i
        return events, totals
    except Exception as exc:  # noqa: BLE001 - reads are best-effort
        logger.warning("get_recent_activity_durable failed: %s", exc)
        buf = get_recent_activity(limit)
        return buf, _tally(list(_events))


def clear_activity() -> None:
    """Drop all in-memory events. Used by tests."""
    _events.clear()
