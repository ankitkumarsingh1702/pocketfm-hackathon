"""Neo4j read/write for the story-canon knowledge graph.

Every function is best-effort (mirrors :mod:`app.db.firestore`): when the graph
is disabled/unreachable, writes no-op and reads return an empty graph, so the
engine behaves exactly as it did before the knowledge graph existed.

Graph model
-----------
Nodes carry a common ``:Canon`` label plus a type label (``:Character``,
``:PlotThread``, ``:Clue``, ``:Location``, ``:Theme``, ``:Episode``,
``:AudienceSegment``, ``:Fact``) and a stable ``key``. Entities are linked to the
episode they appear in via ``MENTIONED_IN``; extracted relations become typed
edges; atomic facts become ``:Fact`` nodes (for later contradiction search);
audience verdicts become ``(:AudienceSegment)-[:REACTED_TO]->(:Episode)`` edges.
"""

from __future__ import annotations

import hashlib
import logging
import re

from app.config import settings
from app.db.activity import record_activity
from app.graph.driver import get_driver
from app.schemas import (
    CanonEdgeView,
    CanonExtraction,
    CanonGraph,
    CanonNodeView,
    CanonResetResult,
    IngestResult,
    Story,
)

logger = logging.getLogger(__name__)

# Type labels we allow as real Neo4j labels (whitelist → safe to interpolate).
_ALLOWED_LABELS = {
    "Character", "PlotThread", "Clue", "Episode", "Location", "Theme", "AudienceSegment",
}
# Node types that make up the injectable "story bible".
_BIBLE_TYPES = ["Character", "PlotThread", "Clue", "Location", "Theme"]


# --- id / sanitisation helpers ----------------------------------------------

def _slug(*parts: object) -> str:
    raw = " ".join(str(p) for p in parts if p)
    s = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    return s or "x"


def _node_id(etype: str, name: str, batch: str | None = None) -> str:
    scope = f"{_slug(batch)}:" if batch else ""
    return f"{etype}:{scope}{_slug(name)}"


def _episode_id(story: Story, batch: str | None = None) -> str:
    scope = f"{_slug(batch)}:" if batch else ""
    return f"Episode:{scope}{_slug(story.title, story.episode or '')}"


def _episode_name(story: Story) -> str:
    return f"{story.title} — {story.episode}" if story.episode else story.title


def _sanitize_rel(rel_type: str) -> str:
    """UPPER_SNAKE, alnum+underscore, letter-initial; fallback RELATES_TO."""
    s = re.sub(r"[^A-Za-z0-9_]", "_", (rel_type or "").strip()).upper().strip("_")
    if not s or not re.match(r"^[A-Z]", s):
        return "RELATES_TO"
    return s


# --- write path -------------------------------------------------------------

async def ingest_extraction(
    story: Story,
    extraction: CanonExtraction,
    source: str = "Canon Ingest",
    batch: str | None = None,
) -> IngestResult:
    """Merge an episode into canon and attach it to an explicit session batch.

    Canon entity keys stay globally stable for entity resolution, but ownership
    never lives on the shared node. A ``CanonBatch`` node owns ``INCLUDES``
    memberships, while extracted relationships carry a list of contributing
    batches. This lets two browser sessions share "Meera" safely: clearing one
    session removes only its membership and never steals/deletes the other's
    canon or the seeded demo.
    """
    batch = (batch or "").strip() or None
    has_batch = batch is not None
    epkey = _episode_id(story, batch=batch)
    names = [e.name for e in extraction.entities if e.type != "Episode"]

    driver = get_driver()
    if driver is None:
        record_activity("skipped", "ingest_extraction", source, "graph disabled — canon not persisted")
        return IngestResult(
            episode_id=epkey,
            nodes_added=0,
            edges_added=0,
            batch=batch or "",
            entities=names,
            extraction=extraction,
        )

    # Map the LLM's transient keys → our stable, deterministic node ids so the
    # same character across episodes resolves to one node (entity resolution).
    keymap: dict[str, str] = {}
    typed_nodes: dict[str, list[dict]] = {}
    for e in extraction.entities:
        if e.type == "Episode":
            keymap[e.key] = epkey  # fold any LLM 'episode' entity into our canonical one
            continue
        nid = _node_id(e.type, e.name, batch=batch)
        keymap[e.key] = nid
        typed_nodes.setdefault(e.type, []).append(
            {"key": nid, "name": e.name, "description": e.description or ""}
        )

    typed_rels: dict[str, list[dict]] = {}
    for r in extraction.relations:
        src, dst = keymap.get(r.source_key), keymap.get(r.target_key)
        if not src or not dst:
            continue
        typed_rels.setdefault(_sanitize_rel(r.type), []).append(
            {"src": src, "dst": dst, "detail": r.detail or ""}
        )

    facts = [
        {
            "key": f"Fact:{_slug(keymap.get(f.subject_key, ''), f.predicate, f.object)}",
            "subject": keymap.get(f.subject_key, ""),
            "predicate": f.predicate,
            "object": f.object,
        }
        for f in extraction.facts
        if f.predicate and f.object
    ]

    nodes_added = edges_added = facts_added = 0
    included_keys = [epkey]

    def _relationship_updates(var: str) -> str:
        return (
            f"ON CREATE SET {var}.session_only=$has_batch "
            f"ON MATCH SET {var}.session_only=coalesce({var}.session_only, false) "
            f"SET {var}.session_only=CASE WHEN $has_batch "
            f"THEN coalesce({var}.session_only, false) ELSE false END, "
            f"{var}.batches=CASE "
            f"WHEN $batch IS NULL THEN coalesce({var}.batches, []) "
            f"WHEN $batch IN coalesce({var}.batches, []) THEN coalesce({var}.batches, []) "
            f"ELSE coalesce({var}.batches, []) + $batch END "
        )

    try:
        async with driver.session(database=settings.neo4j_database) as session:
            summary = await (
                await session.run(
                    "MERGE (e:Canon:Episode {key:$k}) "
                    "ON CREATE SET e.created_by_session=$batch "
                    "SET e.type='Episode', e.name=$n, e.title=$t, e.episode=$ep, "
                    "e.created_by_session=CASE WHEN $has_batch "
                    "THEN e.created_by_session ELSE null END",
                    k=epkey,
                    n=_episode_name(story),
                    t=story.title,
                    ep=story.episode or "",
                    batch=batch,
                    has_batch=has_batch,
                )
            ).consume()
            nodes_added += summary.counters.nodes_created

            for etype, rows in typed_nodes.items():
                label = etype if etype in _ALLOWED_LABELS else "Entity"
                query = (
                    "UNWIND $rows AS row "
                    "MERGE (n:Canon {key: row.key}) "
                    "ON CREATE SET n.created_by_session=$batch "
                    f"SET n:{label}, n.type=$etype, n.name=row.name, n.description=row.description, "
                    "n.created_by_session=CASE WHEN $has_batch "
                    "THEN n.created_by_session ELSE null END "
                    "WITH n MATCH (e:Canon:Episode {key:$ep}) "
                    "MERGE (n)-[r:MENTIONED_IN]->(e) "
                    + _relationship_updates("r")
                )
                summary = await (
                    await session.run(
                        query,
                        rows=rows,
                        etype=etype,
                        ep=epkey,
                        batch=batch,
                        has_batch=has_batch,
                    )
                ).consume()
                nodes_added += summary.counters.nodes_created
                edges_added += summary.counters.relationships_created
                included_keys.extend(row["key"] for row in rows)

            for rtype, rows in typed_rels.items():
                query = (
                    "UNWIND $rows AS row "
                    "MATCH (a:Canon {key: row.src}), (b:Canon {key: row.dst}) "
                    f"MERGE (a)-[r:{rtype}]->(b) "
                    + _relationship_updates("r")
                    + "SET r.detail = row.detail"
                )
                summary = await (
                    await session.run(
                        query,
                        rows=rows,
                        batch=batch,
                        has_batch=has_batch,
                    )
                ).consume()
                edges_added += summary.counters.relationships_created

            if facts:
                node_query = (
                    "UNWIND $rows AS row "
                    "MERGE (f:Canon:Fact {key: row.key}) "
                    "ON CREATE SET f.created_by_session=$batch "
                    "SET f.type='Fact', f.name=row.predicate, f.subject_key=row.subject, "
                    "f.predicate=row.predicate, f.object=row.object, "
                    "f.created_by_session=CASE WHEN $has_batch "
                    "THEN f.created_by_session ELSE null END"
                )
                summary = await (
                    await session.run(
                        node_query,
                        rows=facts,
                        batch=batch,
                        has_batch=has_batch,
                    )
                ).consume()
                facts_added += summary.counters.nodes_created
                nodes_added += summary.counters.nodes_created

                episode_rel_query = (
                    "UNWIND $rows AS row "
                    "MATCH (f:Canon:Fact {key:row.key}), (e:Canon:Episode {key:$ep}) "
                    "MERGE (f)-[r:IN_EPISODE]->(e) "
                    + _relationship_updates("r")
                )
                summary = await (
                    await session.run(
                        episode_rel_query,
                        rows=facts,
                        ep=epkey,
                        batch=batch,
                        has_batch=has_batch,
                    )
                ).consume()
                edges_added += summary.counters.relationships_created

                asserts_query = (
                    "UNWIND $rows AS row "
                    "MATCH (f:Canon:Fact {key:row.key}), (s:Canon {key:row.subject}) "
                    "MERGE (s)-[r:ASSERTS]->(f) "
                    + _relationship_updates("r")
                )
                summary = await (
                    await session.run(
                        asserts_query,
                        rows=facts,
                        batch=batch,
                        has_batch=has_batch,
                    )
                ).consume()
                edges_added += summary.counters.relationships_created
                included_keys.extend(row["key"] for row in facts)

            if batch:
                await (
                    await session.run(
                        "MERGE (cb:CanonBatch {id:$batch}) "
                        "SET cb.updated_at=timestamp() "
                        "WITH cb UNWIND $keys AS key "
                        "MATCH (n:Canon {key:key}) "
                        "MERGE (cb)-[:INCLUDES]->(n)",
                        batch=batch,
                        keys=sorted(set(included_keys)),
                    )
                ).consume()
    except Exception as exc:  # noqa: BLE001 - persistence is strictly best-effort
        logger.warning("Canon ingest failed: %s", exc)
        record_activity("skipped", "ingest_extraction", source, f"ingest failed: {exc}")
        return IngestResult(
            episode_id=epkey,
            nodes_added=0,
            edges_added=0,
            batch=batch or "",
            entities=names,
            extraction=extraction,
        )

    record_activity(
        "write",
        "ingest_extraction",
        source,
        f"wrote canon +{nodes_added} nodes / +{edges_added} edges / +{facts_added} facts "
        f"from {_episode_name(story)}",
        {
            "nodes_added": nodes_added,
            "edges_added": edges_added,
            "facts_added": facts_added,
        },
    )
    return IngestResult(
        episode_id=epkey,
        nodes_added=nodes_added,
        edges_added=edges_added,
        facts_added=facts_added,
        batch=batch or "",
        entities=names,
        extraction=extraction,
    )


async def write_audience_verdict(
    story: Story, segments: list[dict], source: str = "Audience"
) -> None:
    """Record per-segment audience verdicts as edges to the episode. Best-effort.

    ``segments`` items: ``{"segment": str, "following_pct": float, "avg_hook": float}``.
    """
    driver = get_driver()
    if driver is None:
        record_activity("skipped", "write_audience_verdict", source, "graph disabled — verdict not persisted")
        return
    if not segments:
        return
    rows = [
        {
            "key": f"AudienceSegment:{_slug(s.get('segment') or 'general')}",
            "name": s.get("segment") or "General",
            "following_pct": float(s.get("following_pct") or 0.0),
            "avg_hook": float(s.get("avg_hook") or 0.0),
        }
        for s in segments
    ]
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            await session.run(
                "MERGE (e:Canon:Episode {key:$ep}) SET e.type='Episode', e.name=$en "
                "WITH e UNWIND $rows AS row "
                "MERGE (seg:Canon:AudienceSegment {key: row.key}) "
                "SET seg.type='AudienceSegment', seg.name=row.name "
                "MERGE (seg)-[r:REACTED_TO]->(e) "
                "SET r.following_pct=row.following_pct, r.avg_hook=row.avg_hook",
                ep=_episode_id(story), en=_episode_name(story), rows=rows,
            )
        avg_follow = round(sum(r["following_pct"] for r in rows) / len(rows), 1)
        record_activity(
            "write",
            "write_audience_verdict",
            source,
            f"wrote audience verdict — {avg_follow}% following across {len(rows)} segment(s)",
            {"segments": len(rows), "following_pct": avg_follow},
        )
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("Audience verdict write-back failed: %s", exc)
        record_activity("skipped", "write_audience_verdict", source, f"write failed: {exc}")


# --- read path --------------------------------------------------------------

async def _run_graph_query(
    node_query: str,
    edge_query: str,
    *,
    source: str = "",
    fn: str = "fetch_graph",
    record: bool = True,
    **params,
) -> CanonGraph:
    """Shared reader: run a node query + edge query into a ``CanonGraph``.

    When ``record`` is true the read is logged to the activity feed (attributed
    to ``source``). The full-graph visualization read passes ``record=False`` so
    that polling the graph view never floods the feed — only agent memory reads
    are surfaced.
    """
    driver = get_driver()
    if driver is None:
        if record:
            record_activity("skipped", fn, source, "graph disabled — no memory to read")
        return CanonGraph()
    try:
        nodes: list[CanonNodeView] = []
        edges: list[CanonEdgeView] = []
        stats: dict[str, int] = {}
        async with driver.session(database=settings.neo4j_database) as session:
            result = await session.run(node_query, **params)
            async for rec in result:
                label = rec.get("label") or "Entity"
                props = {}
                if rec.get("description"):
                    props["description"] = rec["description"]
                nodes.append(
                    CanonNodeView(
                        id=rec["id"], label=label, name=rec.get("name") or rec["id"], props=props
                    )
                )
                stats[label] = stats.get(label, 0) + 1
            result = await session.run(edge_query, **params)
            async for rec in result:
                edges.append(
                    CanonEdgeView(
                        source=rec["source"],
                        target=rec["target"],
                        type=rec["type"],
                        detail=rec.get("detail") or "",
                    )
                )
        stats["edges"] = len(edges)
        if record:
            record_activity(
                "read",
                fn,
                source,
                f"read {len(nodes)} nodes + {len(edges)} edges from shared memory",
                {"nodes": len(nodes), "edges": len(edges)},
            )
        return CanonGraph(nodes=nodes, edges=edges, stats=stats)
    except Exception as exc:  # noqa: BLE001 - reads are best-effort
        logger.warning("Canon read failed: %s", exc)
        if record:
            record_activity("skipped", fn, source, f"read failed: {exc}")
        return CanonGraph()


async def fetch_contradiction_candidates(
    source: str = "Plot Hole Hunter",
    record: bool = True,
    batch: str | None = None,
) -> dict:
    """Graph-traversal candidates for continuity checking. Best-effort.

    Returns ``{facts, conflicts, dangling_clues, episode_count, fact_count}``
    where ``conflicts`` are same-subject+predicate facts with different objects
    (the structural contradictions, each carrying the two episodes it spans as
    ``ep_a``/``ep_b``), and ``dangling_clues`` are clues introduced but never
    advanced/paid off. ``fact_count`` is the true total (the ``facts`` list is a
    capped sample for prompting). These ground the LLM plot-hole verifier.
    """
    batch = (batch or "").strip() or None
    empty = {
        "facts": [], "conflicts": [], "dangling_clues": [],
        "episode_count": 0, "fact_count": 0,
    }
    driver = get_driver()
    if driver is None:
        if record:
            record_activity("skipped", "fetch_contradiction_candidates", source, "graph disabled — no facts to traverse")
        return empty
    out = {
        "facts": [], "conflicts": [], "dangling_clues": [],
        "episode_count": 0, "fact_count": 0,
    }
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            if batch:
                facts_query = (
                    "MATCH (cb:CanonBatch {id:$batch})-[:INCLUDES]->(f:Fact) "
                    "OPTIONAL MATCH (cb)-[:INCLUDES]->(subj:Canon {key:f.subject_key}) "
                    "RETURN coalesce(subj.name, f.subject_key) AS subject, "
                    "f.predicate AS predicate, f.object AS object LIMIT 200"
                )
            else:
                facts_query = (
                    "MATCH (f:Fact) OPTIONAL MATCH (subj:Canon {key:f.subject_key}) "
                    "RETURN coalesce(subj.name, f.subject_key) AS subject, "
                    "f.predicate AS predicate, f.object AS object LIMIT 200"
                )
            res = await session.run(facts_query, batch=batch)
            async for r in res:
                out["facts"].append(
                    {"subject": r["subject"], "predicate": r["predicate"], "object": r["object"]}
                )

            # Group facts by (subject, predicate); any group with >1 distinct
            # object is a structural contradiction. Carry the episode each side
            # came from (as a display label) so findings can cite "Ep 4 ↔ Ep 41"
            # — this is the cross-episode reasoning a human can't do by hand.
            # Ordered earliest-episode-first so ep_a precedes ep_b.
            conflict_prefix = (
                "MATCH (cb:CanonBatch {id:$batch})-[:INCLUDES]->(f:Fact) "
                "MATCH (f)-[rel:IN_EPISODE]->(e:Episode) "
                "WHERE $batch IN coalesce(rel.batches, []) "
                "AND EXISTS { MATCH (cb)-[:INCLUDES]->(e) } "
                if batch
                else "MATCH (f:Fact)-[:IN_EPISODE]->(e:Episode) "
            )
            res = await session.run(
                conflict_prefix
                +
                "WITH f.subject_key AS sk, f.predicate AS pred, f.object AS obj, "
                "  min(coalesce(e.epnum, 9999)) AS epnum, "
                "  head(collect(coalesce(e.episode, e.name, e.title))) AS eplabel "
                "ORDER BY epnum "
                "WITH sk, pred, collect(obj) AS objs, collect(epnum) AS epnums, "
                "  collect(eplabel) AS eplabels "
                "WHERE size(objs) > 1 "
                "OPTIONAL MATCH (subj:Canon {key: sk}) "
                "RETURN coalesce(subj.name, sk) AS subject, pred AS predicate, "
                "  objs[0] AS a, objs[1] AS b, "
                "  CASE WHEN epnums[0] < 9999 THEN 'Ep ' + toString(epnums[0]) "
                "    ELSE coalesce(eplabels[0], '?') END AS ep_a, "
                "  CASE WHEN epnums[1] < 9999 THEN 'Ep ' + toString(epnums[1]) "
                "    ELSE coalesce(eplabels[1], '?') END AS ep_b "
                "LIMIT 50",
                batch=batch,
            )
            async for r in res:
                out["conflicts"].append(
                    {
                        "subject": r["subject"], "predicate": r["predicate"],
                        "a": r["a"], "b": r["b"], "ep_a": r["ep_a"], "ep_b": r["ep_b"],
                    }
                )

            # A clue is "dangling" if it has no outgoing edge other than the
            # MENTIONED_IN link to its episode (i.e. never advanced/paid off).
            clue_query = (
                "MATCH (cb:CanonBatch {id:$batch})-[:INCLUDES]->(c:Clue) "
                "OPTIONAL MATCH (c)-[r]->(target:Canon) "
                "WHERE type(r) <> 'MENTIONED_IN' "
                "AND $batch IN coalesce(r.batches, []) "
                "AND EXISTS { MATCH (cb)-[:INCLUDES]->(target) } "
                "WITH c, count(r) AS outdeg WHERE outdeg = 0 "
                "RETURN c.name AS name LIMIT 50"
                if batch
                else
                "MATCH (c:Clue) "
                "OPTIONAL MATCH (c)-[r]->(:Canon) WHERE type(r) <> 'MENTIONED_IN' "
                "WITH c, count(r) AS outdeg WHERE outdeg = 0 "
                "RETURN c.name AS name LIMIT 50"
            )
            res = await session.run(clue_query, batch=batch)
            async for r in res:
                out["dangling_clues"].append(r["name"])

            episode_query = (
                "MATCH (:CanonBatch {id:$batch})-[:INCLUDES]->(e:Episode) "
                "RETURN count(DISTINCT e) AS c"
                if batch
                else "MATCH (e:Episode) RETURN count(e) AS c"
            )
            rec = await (await session.run(episode_query, batch=batch)).single()
            out["episode_count"] = rec["c"] if rec else 0
            count_query = (
                "MATCH (:CanonBatch {id:$batch})-[:INCLUDES]->(f:Fact) "
                "RETURN count(DISTINCT f) AS c"
                if batch
                else "MATCH (f:Fact) RETURN count(f) AS c"
            )
            rec = await (await session.run(count_query, batch=batch)).single()
            out["fact_count"] = rec["c"] if rec else 0
        if record:
            record_activity(
                "read",
                "fetch_contradiction_candidates",
                source,
                f"traversed {out['fact_count']} facts across {out['episode_count']} episodes "
                f"— {len(out['conflicts'])} contradiction(s), {len(out['dangling_clues'])} dangling clue(s)",
                {
                    "facts": out["fact_count"],
                    "episodes": out["episode_count"],
                    "conflicts": len(out["conflicts"]),
                    "dangling_clues": len(out["dangling_clues"]),
                },
            )
        return out
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("Contradiction candidate query failed: %s", exc)
        if record:
            record_activity("skipped", "fetch_contradiction_candidates", source, f"traversal failed: {exc}")
        return empty


async def fetch_full_graph(
    record: bool = False,
    batch: str | None = None,
) -> CanonGraph:
    """The entire canon graph, for the visualization tab.

    Defaults to ``record=False`` so that the graph view (which the DB / Memory
    tab polls continuously) never floods the activity feed — the feed is meant to
    show agent memory reads and writes, not the visualization polling itself.
    """
    batch = (batch or "").strip() or None
    node_query = (
        "MATCH (:CanonBatch {id:$batch})-[:INCLUDES]->(n:Canon) "
        "RETURN DISTINCT n.key AS id, coalesce(n.type,'Entity') AS label, "
        "coalesce(n.name,n.key) AS name, n.description AS description LIMIT 500"
        if batch
        else
        "MATCH (n:Canon) RETURN n.key AS id, coalesce(n.type,'Entity') AS label, "
        "coalesce(n.name,n.key) AS name, n.description AS description LIMIT 500"
    )
    edge_query = (
        "MATCH (cb:CanonBatch {id:$batch})-[:INCLUDES]->(a:Canon)-[r]->(b:Canon) "
        "WHERE $batch IN coalesce(r.batches, []) "
        "AND EXISTS { MATCH (cb)-[:INCLUDES]->(b) } "
        "RETURN DISTINCT a.key AS source, b.key AS target, type(r) AS type, "
        "r.detail AS detail LIMIT 1500"
        if batch
        else
        "MATCH (a:Canon)-[r]->(b:Canon) "
        "RETURN a.key AS source, b.key AS target, type(r) AS type, r.detail AS detail LIMIT 1500"
    )
    graph = await _run_graph_query(
        node_query,
        edge_query,
        source="Graph View",
        fn="fetch_full_graph",
        record=record,
        batch=batch,
    )
    # The node query is capped at 500 for the visualization, which undercounts
    # Fact nodes (a large canon has thousands). Overwrite the Fact stat with the
    # true total so "facts tracked" reflects the whole canon, not the sample.
    driver = get_driver()
    if driver is not None:
        try:
            async with driver.session(database=settings.neo4j_database) as session:
                fact_query = (
                    "MATCH (:CanonBatch {id:$batch})-[:INCLUDES]->(f:Fact) "
                    "RETURN count(DISTINCT f) AS c"
                    if batch
                    else "MATCH (f:Fact) RETURN count(f) AS c"
                )
                rec = await (await session.run(fact_query, batch=batch)).single()
                if rec is not None:
                    graph.stats["Fact"] = rec["c"]
        except Exception as exc:  # noqa: BLE001 - best-effort; keep the capped count on failure
            logger.warning("Fact-count query failed: %s", exc)
    return graph


async def reset_canon_batch(
    batch: str,
    source: str = "Story Canon",
) -> CanonResetResult:
    """Remove one browser session's graph membership without touching shared canon."""
    batch = (batch or "").strip()
    if not batch:
        return CanonResetResult(batch="")
    driver = get_driver()
    if driver is None:
        record_activity(
            "skipped",
            "reset_canon_batch",
            source,
            "graph disabled — nothing to reset",
        )
        return CanonResetResult(batch=batch)

    relationships_deleted = memberships_deleted = nodes_deleted = 0
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            await (
                await session.run(
                    "MATCH ()-[r]->() WHERE $batch IN coalesce(r.batches, []) "
                    "SET r.batches=[item IN r.batches WHERE item <> $batch]",
                    batch=batch,
                )
            ).consume()
            summary = await (
                await session.run(
                    "MATCH ()-[r]->() "
                    "WHERE coalesce(r.session_only, false)=true "
                    "AND size(coalesce(r.batches, []))=0 DELETE r"
                )
            ).consume()
            relationships_deleted = summary.counters.relationships_deleted

            summary = await (
                await session.run(
                    "MATCH (cb:CanonBatch {id:$batch})-[m:INCLUDES]->(:Canon) DELETE m",
                    batch=batch,
                )
            ).consume()
            memberships_deleted = summary.counters.relationships_deleted
            await (
                await session.run(
                    "MATCH (cb:CanonBatch {id:$batch}) DELETE cb",
                    batch=batch,
                )
            ).consume()

            summary = await (
                await session.run(
                    "MATCH (n:Canon) "
                    "WHERE n.created_by_session IS NOT NULL "
                    "AND n.seed_batch IS NULL "
                    "AND NOT EXISTS { MATCH (:CanonBatch)-[:INCLUDES]->(n) } "
                    "AND NOT (n)--() "
                    "DELETE n"
                )
            ).consume()
            nodes_deleted = summary.counters.nodes_deleted
    except Exception as exc:  # noqa: BLE001 - cleanup is best-effort but scoped
        logger.warning("Session canon reset failed: %s", exc)
        record_activity("skipped", "reset_canon_batch", source, f"reset failed: {exc}")
        return CanonResetResult(batch=batch)

    record_activity(
        "write",
        "reset_canon_batch",
        source,
        f"cleared only session {batch}: {memberships_deleted} memberships, "
        f"{relationships_deleted} session edges, {nodes_deleted} orphan nodes",
        {
            "memberships_deleted": memberships_deleted,
            "relationships_deleted": relationships_deleted,
            "nodes_deleted": nodes_deleted,
        },
    )
    return CanonResetResult(
        batch=batch,
        nodes_deleted=nodes_deleted,
        relationships_deleted=relationships_deleted,
        memberships_deleted=memberships_deleted,
    )


async def fetch_canon_subgraph(
    story: Story,
    source: str = "",
    batch: str | None = None,
) -> CanonGraph:
    """The story-bible slice used to ground prompts (characters/threads/clues…).

    ``source`` names the agent/lens reading this shared memory, so the DB / Memory
    tab can attribute the read.
    """
    batch = (batch or "").strip() or None
    node_query = (
        "MATCH (:CanonBatch {id:$batch})-[:INCLUDES]->(n:Canon) "
        "WHERE n.type IN $types "
        "RETURN DISTINCT n.key AS id, n.type AS label, n.name AS name, "
        "n.description AS description LIMIT 120"
        if batch
        else
        "MATCH (n:Canon) WHERE n.type IN $types "
        "RETURN n.key AS id, n.type AS label, n.name AS name, "
        "n.description AS description LIMIT 120"
    )
    edge_query = (
        "MATCH (cb:CanonBatch {id:$batch})-[:INCLUDES]->(a:Canon)-[r]->(b:Canon) "
        "WHERE a.type IN $types AND b.type IN $types "
        "AND $batch IN coalesce(r.batches, []) "
        "AND EXISTS { MATCH (cb)-[:INCLUDES]->(b) } "
        "RETURN DISTINCT a.key AS source, b.key AS target, type(r) AS type, "
        "r.detail AS detail LIMIT 400"
        if batch
        else
        "MATCH (a:Canon)-[r]->(b:Canon) "
        "WHERE a.type IN $types AND b.type IN $types "
        "RETURN a.key AS source, b.key AS target, type(r) AS type, "
        "r.detail AS detail LIMIT 400"
    )
    return await _run_graph_query(
        node_query,
        edge_query,
        source=source,
        fn="fetch_canon_subgraph",
        types=_BIBLE_TYPES,
        batch=batch,
    )


# --- memory rendering -------------------------------------------------------

def render_canon_memory(graph: CanonGraph) -> str:
    """Render a compact 'story bible' text block for prompt injection.

    Returns ``""`` when the graph is empty, so callers can cheaply detect the
    no-memory case (and keep today's behaviour).
    """
    if not graph.nodes:
        return ""

    by_type: dict[str, list[CanonNodeView]] = {}
    for n in graph.nodes:
        by_type.setdefault(n.label, []).append(n)

    def _line(n: CanonNodeView) -> str:
        desc = n.props.get("description")
        return f"{n.name} — {desc}" if desc else n.name

    order = [
        ("Character", "Characters"),
        ("PlotThread", "Open threads"),
        ("Clue", "Clues"),
        ("Location", "Locations"),
        ("Theme", "Themes"),
    ]
    parts = ["STORY SO FAR — canon you remember from earlier episodes of this show:"]
    for key, heading in order:
        items = by_type.get(key)
        if items:
            parts.append(f"{heading}: " + "; ".join(_line(n) for n in items))

    # A few key relationships, if any, for connective tissue.
    name_by_id = {n.id: n.name for n in graph.nodes}
    rels = [
        f"{name_by_id.get(e.source, e.source)} {e.type.replace('_', ' ').lower()} "
        f"{name_by_id.get(e.target, e.target)}"
        for e in graph.edges[:10]
    ]
    if rels:
        parts.append("Known connections: " + "; ".join(rels) + ".")

    text = "\n".join(parts)
    limit = settings.canon_max_chars
    return text[:limit] if len(text) > limit else text


def canon_fingerprint(canon: str) -> str:
    """Stable 16-hex digest of the injected canon, or ``"nocanon"`` when empty.

    Folded into reaction cache keys so that injecting (or changing) memory never
    replays a reaction cached under different / no canon.
    """
    if not canon:
        return "nocanon"
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]
