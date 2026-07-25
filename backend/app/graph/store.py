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
from app.graph.driver import get_driver
from app.schemas import (
    CanonEdgeView,
    CanonExtraction,
    CanonGraph,
    CanonNodeView,
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


def _node_id(etype: str, name: str) -> str:
    return f"{etype}:{_slug(name)}"


def _episode_id(story: Story) -> str:
    return f"Episode:{_slug(story.title, story.episode or '')}"


def _episode_name(story: Story) -> str:
    return f"{story.title} — {story.episode}" if story.episode else story.title


def _sanitize_rel(rel_type: str) -> str:
    """UPPER_SNAKE, alnum+underscore, letter-initial; fallback RELATES_TO."""
    s = re.sub(r"[^A-Za-z0-9_]", "_", (rel_type or "").strip()).upper().strip("_")
    if not s or not re.match(r"^[A-Z]", s):
        return "RELATES_TO"
    return s


# --- write path -------------------------------------------------------------

async def ingest_extraction(story: Story, extraction: CanonExtraction) -> IngestResult:
    """Merge an episode's extracted canon into Neo4j (idempotent). Best-effort."""
    epkey = _episode_id(story)
    names = [e.name for e in extraction.entities if e.type != "Episode"]

    driver = get_driver()
    if driver is None:
        return IngestResult(episode_id=epkey, nodes_added=0, edges_added=0, entities=names)

    # Map the LLM's transient keys → our stable, deterministic node ids so the
    # same character across episodes resolves to one node (entity resolution).
    keymap: dict[str, str] = {}
    typed_nodes: dict[str, list[dict]] = {}
    for e in extraction.entities:
        if e.type == "Episode":
            keymap[e.key] = epkey  # fold any LLM 'episode' entity into our canonical one
            continue
        nid = _node_id(e.type, e.name)
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
            "key": f"Fact:{_slug(f.subject_key, f.predicate, f.object)}",
            "subject": keymap.get(f.subject_key, ""),
            "predicate": f.predicate,
            "object": f.object,
        }
        for f in extraction.facts
        if f.predicate and f.object
    ]

    nodes_added = edges_added = 0
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            summary = await (
                await session.run(
                    "MERGE (e:Canon:Episode {key:$k}) "
                    "SET e.type='Episode', e.name=$n, e.title=$t, e.episode=$ep",
                    k=epkey, n=_episode_name(story), t=story.title, ep=story.episode or "",
                )
            ).consume()
            nodes_added += summary.counters.nodes_created

            for etype, rows in typed_nodes.items():
                label = etype if etype in _ALLOWED_LABELS else "Entity"
                query = (
                    "UNWIND $rows AS row "
                    "MERGE (n:Canon {key: row.key}) "
                    f"SET n:{label}, n.type=$etype, n.name=row.name, n.description=row.description "
                    "WITH n MATCH (e:Canon:Episode {key:$ep}) "
                    "MERGE (n)-[:MENTIONED_IN]->(e)"
                )
                summary = await (
                    await session.run(query, rows=rows, etype=etype, ep=epkey)
                ).consume()
                nodes_added += summary.counters.nodes_created
                edges_added += summary.counters.relationships_created

            for rtype, rows in typed_rels.items():
                query = (
                    "UNWIND $rows AS row "
                    "MATCH (a:Canon {key: row.src}), (b:Canon {key: row.dst}) "
                    f"MERGE (a)-[r:{rtype}]->(b) SET r.detail = row.detail"
                )
                summary = await (await session.run(query, rows=rows)).consume()
                edges_added += summary.counters.relationships_created

            if facts:
                query = (
                    "UNWIND $rows AS row "
                    "MERGE (f:Canon:Fact {key: row.key}) "
                    "SET f.type='Fact', f.name=row.predicate, f.subject_key=row.subject, "
                    "f.predicate=row.predicate, f.object=row.object "
                    "WITH f, row MATCH (e:Canon:Episode {key:$ep}) "
                    "MERGE (f)-[:IN_EPISODE]->(e) "
                    "WITH f, row OPTIONAL MATCH (s:Canon {key: row.subject}) "
                    "FOREACH (_ IN CASE WHEN s IS NULL THEN [] ELSE [1] END | "
                    "MERGE (s)-[:ASSERTS]->(f))"
                )
                summary = await (await session.run(query, rows=facts, ep=epkey)).consume()
                nodes_added += summary.counters.nodes_created
                edges_added += summary.counters.relationships_created
    except Exception as exc:  # noqa: BLE001 - persistence is strictly best-effort
        logger.warning("Canon ingest failed: %s", exc)
        return IngestResult(episode_id=epkey, nodes_added=0, edges_added=0, entities=names)

    return IngestResult(
        episode_id=epkey, nodes_added=nodes_added, edges_added=edges_added, entities=names
    )


async def write_audience_verdict(story: Story, segments: list[dict]) -> None:
    """Record per-segment audience verdicts as edges to the episode. Best-effort.

    ``segments`` items: ``{"segment": str, "following_pct": float, "avg_hook": float}``.
    """
    driver = get_driver()
    if driver is None or not segments:
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
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("Audience verdict write-back failed: %s", exc)


# --- read path --------------------------------------------------------------

async def _run_graph_query(node_query: str, edge_query: str, **params) -> CanonGraph:
    """Shared reader: run a node query + edge query into a ``CanonGraph``."""
    driver = get_driver()
    if driver is None:
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
                    CanonEdgeView(source=rec["source"], target=rec["target"], type=rec["type"])
                )
        stats["edges"] = len(edges)
        return CanonGraph(nodes=nodes, edges=edges, stats=stats)
    except Exception as exc:  # noqa: BLE001 - reads are best-effort
        logger.warning("Canon read failed: %s", exc)
        return CanonGraph()


async def fetch_contradiction_candidates() -> dict:
    """Graph-traversal candidates for continuity checking. Best-effort.

    Returns ``{facts, conflicts, dangling_clues, episode_count}`` where
    ``conflicts`` are same-subject+predicate facts with different objects (the
    structural contradictions), and ``dangling_clues`` are clues introduced but
    never advanced/paid off. These ground the LLM plot-hole verifier.
    """
    empty = {"facts": [], "conflicts": [], "dangling_clues": [], "episode_count": 0}
    driver = get_driver()
    if driver is None:
        return empty
    out = {"facts": [], "conflicts": [], "dangling_clues": [], "episode_count": 0}
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            res = await session.run(
                "MATCH (f:Fact) OPTIONAL MATCH (subj:Canon {key: f.subject_key}) "
                "RETURN coalesce(subj.name, f.subject_key) AS subject, "
                "f.predicate AS predicate, f.object AS object LIMIT 200"
            )
            async for r in res:
                out["facts"].append(
                    {"subject": r["subject"], "predicate": r["predicate"], "object": r["object"]}
                )

            res = await session.run(
                "MATCH (f1:Fact), (f2:Fact) "
                "WHERE f1.subject_key = f2.subject_key AND f1.predicate = f2.predicate "
                "AND f1.object < f2.object "
                "OPTIONAL MATCH (subj:Canon {key: f1.subject_key}) "
                "RETURN coalesce(subj.name, f1.subject_key) AS subject, "
                "f1.predicate AS predicate, f1.object AS a, f2.object AS b LIMIT 50"
            )
            async for r in res:
                out["conflicts"].append(
                    {"subject": r["subject"], "predicate": r["predicate"], "a": r["a"], "b": r["b"]}
                )

            # A clue is "dangling" if it has no outgoing edge other than the
            # MENTIONED_IN link to its episode (i.e. never advanced/paid off).
            res = await session.run(
                "MATCH (c:Clue) "
                "OPTIONAL MATCH (c)-[r]->(:Canon) WHERE type(r) <> 'MENTIONED_IN' "
                "WITH c, count(r) AS outdeg WHERE outdeg = 0 "
                "RETURN c.name AS name LIMIT 50"
            )
            async for r in res:
                out["dangling_clues"].append(r["name"])

            rec = await (await session.run("MATCH (e:Episode) RETURN count(e) AS c")).single()
            out["episode_count"] = rec["c"] if rec else 0
        return out
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("Contradiction candidate query failed: %s", exc)
        return empty


async def fetch_full_graph() -> CanonGraph:
    """The entire canon graph, for the visualization tab."""
    return await _run_graph_query(
        "MATCH (n:Canon) RETURN n.key AS id, coalesce(n.type,'Entity') AS label, "
        "coalesce(n.name,n.key) AS name, n.description AS description LIMIT 500",
        "MATCH (a:Canon)-[r]->(b:Canon) "
        "RETURN a.key AS source, b.key AS target, type(r) AS type LIMIT 1500",
    )


async def fetch_canon_subgraph(story: Story) -> CanonGraph:
    """The story-bible slice used to ground prompts (characters/threads/clues…)."""
    return await _run_graph_query(
        "MATCH (n:Canon) WHERE n.type IN $types "
        "RETURN n.key AS id, n.type AS label, n.name AS name, n.description AS description "
        "LIMIT 120",
        "MATCH (a:Canon)-[r]->(b:Canon) WHERE a.type IN $types AND b.type IN $types "
        "RETURN a.key AS source, b.key AS target, type(r) AS type LIMIT 400",
        types=_BIBLE_TYPES,
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
