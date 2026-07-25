"""Best-effort Neo4j driver access for the knowledge graph.

Mirrors the graceful-degradation contract of :mod:`app.db.firestore`: if the
graph is disabled or unreachable (no credentials, no network, the ``neo4j``
package missing, a bad URI, …) every accessor returns ``None``/``False``
instead of raising. Callers treat that as "no canon", so the engine keeps
working with empty memory exactly as it did before the knowledge graph existed.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING

from app.config import settings

if TYPE_CHECKING:  # pragma: no cover - typing only
    from neo4j import AsyncDriver

logger = logging.getLogger(__name__)


def graph_enabled() -> bool:
    """True when the knowledge graph is switched on AND credentials are present."""
    return settings.use_graph and settings.graph_configured


@lru_cache(maxsize=1)
def get_driver() -> "AsyncDriver | None":
    """Return a cached async Neo4j driver, or ``None`` if unavailable.

    Never raises: a disabled graph, a missing ``neo4j`` package, bad
    credentials, or a construction error all degrade to ``None``. The driver
    connects lazily on first query, so this is safe to call outside a running
    event loop (e.g. from the ``/health`` route wiring).
    """
    if not graph_enabled():
        return None
    try:
        from neo4j import AsyncGraphDatabase

        return AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
        )
    except Exception as exc:  # noqa: BLE001 - graph access is strictly best-effort
        logger.warning("Neo4j driver construction failed: %s", exc)
        return None


async def graph_probe() -> bool:
    """Return True if a trivial ``RETURN 1`` round-trips; never raises.

    Used by the canon health route to report live reachability (as opposed to
    ``graph_enabled()``, which only reports that credentials are configured).
    """
    driver = get_driver()
    if driver is None:
        return False
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            result = await session.run("RETURN 1 AS ok")
            record = await result.single()
            return bool(record and record["ok"] == 1)
    except Exception as exc:  # noqa: BLE001 - probe is strictly best-effort
        logger.warning("Neo4j probe failed: %s", exc)
        return False
