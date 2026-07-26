"""Neo4j persistence for the A2A Word-of-Mouth cascade (a NEW, isolated lens).

Additive graph model, layered on the SAME persisted ``AudienceMember`` population
the Audience Simulator already writes (see :mod:`app.graph.audience_store`). It
adds two edge types and touches nothing existing:

* ``(:AudienceMember)-[:FOLLOWS]->(:AudienceMember)`` — the social graph
  (homophily): who sees whom's activity. Best-effort, idempotent ``MERGE``.
* ``(:AudienceMember)-[:INFLUENCED {post_key,comment,round}]->(:AudienceMember)``
  — proof that agent A's actual comment reached agent B during one cascade. This
  is the persisted record of genuine agent-to-agent communication.

Edges are between plain ``AudienceMember`` nodes (NOT ``:Canon``), so the capped
story-canon visualization is never flooded, and NOTHING is ever deleted — the
seeded demo canon stays untouched. Every function is best-effort: with the graph
disabled/unreachable, writes no-op, exactly like the other stores.
"""

from __future__ import annotations

import logging
import time

from app.config import settings
from app.db.activity import record_activity
from app.graph.audience_store import post_key, upsert_post
from app.graph.driver import get_driver
from app.graph.store import _slug
from app.schemas import Story

logger = logging.getLogger(__name__)

# Bound a single write so a large network can't blow the query size.
_MAX_FOLLOW_EDGES = 6000
_MAX_INFLUENCE_EDGES = 4000


def _member_key(member_id: str) -> str:
    """AudienceMember node key from a persona id (matches audience_store)."""
    return f"AudienceMember:{_slug(member_id)}"


async def save_follow_edges(
    adjacency: dict[str, list[str]], source: str = "A2A Word-of-Mouth"
) -> int:
    """MERGE ``FOLLOWS`` edges for the homophily social graph. Best-effort.

    ``adjacency`` maps a persona id to the ids it is connected to. Only matches
    members that already exist as nodes, so it silently skips any that were never
    persisted. Returns the number of edge rows submitted.
    """
    driver = get_driver()
    if driver is None:
        record_activity("skipped", "save_follow_edges", source, "graph disabled — social graph not persisted")
        return 0
    rows = [
        {"a_key": _member_key(a_id), "b_key": _member_key(b_id)}
        for a_id, neighbours in adjacency.items()
        for b_id in neighbours
        if a_id != b_id
    ][:_MAX_FOLLOW_EDGES]
    if not rows:
        return 0
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            await session.run(
                "UNWIND $rows AS row "
                "MATCH (a:AudienceMember {key: row.a_key}) "
                "MATCH (b:AudienceMember {key: row.b_key}) "
                "MERGE (a)-[:FOLLOWS]->(b)",
                rows=rows,
            )
        record_activity(
            "write",
            "save_follow_edges",
            source,
            f"wrote {len(rows)} FOLLOWS edge(s) into the agent social graph",
            {"edges": len(rows)},
        )
        return len(rows)
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("save_follow_edges failed: %s", exc)
        record_activity("skipped", "save_follow_edges", source, f"write failed: {exc}")
        return 0


async def write_influence_edges(
    story: Story, influence: list[dict], source: str = "A2A Word-of-Mouth"
) -> int:
    """Persist agent-to-agent influence for one cascade. Best-effort.

    ``influence`` is a list of ``{source_id, target_id, round, comment}`` — each
    an edge where the source agent's comment reached (and helped expose) the
    target. Keyed on the post so re-running the same post updates in place.
    Returns the number of edge rows submitted.
    """
    driver = get_driver()
    if driver is None:
        record_activity("skipped", "write_influence_edges", source, "graph disabled — influence not persisted")
        return 0
    if not influence:
        return 0
    pkey = post_key(story)
    rows = [
        {
            "a_key": _member_key(e["source_id"]),
            "b_key": _member_key(e["target_id"]),
            "round": int(e.get("round", 0)),
            "comment": (e.get("comment") or "")[:300],
        }
        for e in influence
    ][:_MAX_INFLUENCE_EDGES]
    try:
        await upsert_post(story, source=source)
        async with driver.session(database=settings.neo4j_database) as session:
            await session.run(
                "UNWIND $rows AS row "
                "MATCH (a:AudienceMember {key: row.a_key}) "
                "MATCH (b:AudienceMember {key: row.b_key}) "
                "MERGE (a)-[r:INFLUENCED {post_key: $pk, target: row.b_key}]->(b) "
                "SET r.round=row.round, r.comment=row.comment, r.created=$now",
                rows=rows,
                pk=pkey,
                now=time.time(),
            )
        record_activity(
            "write",
            "write_influence_edges",
            source,
            f"wrote {len(rows)} agent-to-agent INFLUENCED edge(s) for this post",
            {"edges": len(rows)},
        )
        return len(rows)
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("write_influence_edges failed: %s", exc)
        record_activity("skipped", "write_influence_edges", source, f"write failed: {exc}")
        return 0
