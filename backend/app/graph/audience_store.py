"""Neo4j persistence for the Audience Simulator ("Living Audience").

Persists the audience as a reusable population in the knowledge graph and, per
run, records each agent's reaction as a graph edge — which is what makes the
agents *stateful across posts*: on a later run an agent recalls how it reacted
before (``recall_member_memory``) and reacts as a returning listener.

Graph model (separate from the story canon so it never pollutes the story-bible
memory injected into prompts):

* ``(:AudienceMember {key,name,segment,age,gender,city,genres,traits,
  system_prompt,temperature})`` — one persisted listener. NOT labelled
  ``:Canon`` so the (capped) canon visualization isn't flooded by thousands of
  members; still first-class, queryable graph nodes.
* ``(:AudienceMember)-[:BELONGS_TO]->(:Canon:AudienceSegment)`` — cohort link.
* ``(:Canon:Post {key,name,text,created})`` — a tested post/teaser.
* ``(:AudienceMember)-[:REACTED_TO {sentiment,engagement,hook_score,
  will_listen,comment,created}]->(:Post)`` — the durable reaction (memory).
* ``(:Canon:AudienceSegment)-[:REACTED_TO {positive_pct,avg_hook,listen_pct}]
  ->(:Post)`` — the segment-level aggregate (shows in the canon graph view).

Every function is best-effort: with the graph disabled/unreachable, writes
no-op and reads return empty, exactly like :mod:`app.graph.store`.
"""

from __future__ import annotations

import logging
import time
from uuid import uuid4

from app.config import settings
from app.db.activity import record_activity
from app.graph.driver import get_driver
from app.graph.store import _slug
from app.schemas import CliffhangerRating, Persona, SocialReaction, Story

logger = logging.getLogger(__name__)


def _member_key(persona: Persona) -> str:
    return f"AudienceMember:{_slug(persona.id or persona.name)}"


def _segment_key(segment: str | None) -> str:
    return f"AudienceSegment:{_slug(segment or 'general')}"


def post_key(story: Story) -> str:
    """Stable key for a tested post (title + a short content digest)."""
    import hashlib

    digest = hashlib.sha256(
        (story.text + (story.image_base64 or "")).encode("utf-8")
    ).hexdigest()[:8]
    return f"Post:{_slug(story.title or 'post')}-{digest}"


def _member_row(p: Persona) -> dict:
    return {
        "key": _member_key(p),
        "id": p.id,
        "name": p.name,
        "segment": p.segment or "General",
        "seg_key": _segment_key(p.segment),
        "age": p.age,
        "gender": p.gender or "",
        "city": p.city or "",
        "genres": list(p.genres),
        "traits": list(p.traits),
        "system_prompt": p.system_prompt,
        "temperature": p.temperature,
    }


# --- write path -------------------------------------------------------------


async def save_audience_members(
    members: list[Persona], source: str = "Persona Synthesis"
) -> int:
    """MERGE audience members + their segment links. Returns members written."""
    driver = get_driver()
    if driver is None:
        record_activity("skipped", "save_audience_members", source, "graph disabled — audience not persisted")
        return 0
    if not members:
        return 0
    rows = [_member_row(p) for p in members]
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            await session.run(
                "UNWIND $rows AS row "
                "MERGE (m:AudienceMember {key: row.key}) "
                "SET m.member_id=row.id, m.name=row.name, m.segment=row.segment, "
                "  m.age=row.age, m.gender=row.gender, m.city=row.city, "
                "  m.genres=row.genres, m.traits=row.traits, "
                "  m.system_prompt=row.system_prompt, m.temperature=row.temperature "
                "MERGE (s:Canon:AudienceSegment {key: row.seg_key}) "
                "SET s.type='AudienceSegment', s.name=row.segment "
                "MERGE (m)-[:BELONGS_TO]->(s)",
                rows=rows,
            )
        record_activity(
            "write",
            "save_audience_members",
            source,
            f"persisted {len(rows)} audience member(s) to the knowledge graph",
            {"members": len(rows)},
        )
        return len(rows)
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("save_audience_members failed: %s", exc)
        record_activity("skipped", "save_audience_members", source, f"write failed: {exc}")
        return 0


async def upsert_post(story: Story, source: str = "Audience Simulator") -> str:
    """MERGE the tested post node; returns its key. Best-effort."""
    key = post_key(story)
    driver = get_driver()
    if driver is None:
        return key
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            await session.run(
                "MERGE (p:Canon:Post {key:$k}) "
                "SET p.type='Post', p.name=$name, p.text=$text, p.show=$show, "
                "  p.has_image=$has_image, p.created=coalesce(p.created,$now)",
                k=key,
                name=story.title or "Untitled post",
                text=(story.text or "")[:2000],
                show=story.title or "Untitled",
                has_image=bool(story.image_base64),
                now=time.time(),
            )
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("upsert_post failed: %s", exc)
    return key


async def write_member_reactions(
    story: Story,
    pairs: list[tuple[Persona, SocialReaction]],
    source: str = "Audience Simulator",
) -> bool:
    """Persist each agent's reaction as a REACTED_TO edge (its memory).

    Writes per-member edges (for later recall) and per-segment aggregate edges
    (for the canon graph view). Best-effort.
    """
    driver = get_driver()
    if driver is None:
        record_activity("skipped", "write_member_reactions", source, "graph disabled — reactions not persisted")
        return False
    if not pairs:
        return False
    pkey = post_key(story)
    now = time.time()
    rows = [
        {
            "member_key": _member_key(p),
            "post_key": pkey,
            "sentiment": r.sentiment,
            "engagement": r.engagement,
            "hook_score": int(r.hook_score),
            "will_listen": bool(r.will_listen),
            "comment": (r.comment or "")[:500],
            "created": now,
        }
        for p, r in pairs
    ]
    # Per-segment aggregate for the graph view.
    seg_acc: dict[str, dict] = {}
    for p, r in pairs:
        acc = seg_acc.setdefault(
            _segment_key(p.segment),
            {"name": p.segment or "General", "n": 0, "hook": 0.0, "pos": 0, "listen": 0},
        )
        acc["n"] += 1
        acc["hook"] += int(r.hook_score)
        acc["pos"] += 1 if r.sentiment in ("love", "like") else 0
        acc["listen"] += 1 if r.will_listen else 0
    seg_rows = [
        {
            "seg_key": k,
            "name": v["name"],
            "post_key": pkey,
            "avg_hook": round(v["hook"] / v["n"], 1) if v["n"] else 0.0,
            "positive_pct": round(100.0 * v["pos"] / v["n"], 1) if v["n"] else 0.0,
            "listen_pct": round(100.0 * v["listen"] / v["n"], 1) if v["n"] else 0.0,
        }
        for k, v in seg_acc.items()
    ]
    try:
        await upsert_post(story, source=source)
        async with driver.session(database=settings.neo4j_database) as session:
            await session.run(
                "MATCH (p:Post {key:$pk}) "
                "UNWIND $rows AS row "
                "MATCH (m:AudienceMember {key: row.member_key}) "
                "MERGE (m)-[r:REACTED_TO {post_key: row.post_key}]->(p) "
                "SET r.sentiment=row.sentiment, r.engagement=row.engagement, "
                "  r.hook_score=row.hook_score, r.will_listen=row.will_listen, "
                "  r.comment=row.comment, r.created=row.created",
                pk=pkey,
                rows=rows,
            )
            await session.run(
                "MATCH (p:Post {key:$pk}) "
                "UNWIND $rows AS row "
                "MERGE (s:Canon:AudienceSegment {key: row.seg_key}) "
                "SET s.type='AudienceSegment', s.name=row.name "
                "MERGE (s)-[r:REACTED_TO]->(p) "
                "SET r.avg_hook=row.avg_hook, r.positive_pct=row.positive_pct, "
                "  r.listen_pct=row.listen_pct",
                pk=pkey,
                rows=seg_rows,
            )
        record_activity(
            "write",
            "write_member_reactions",
            source,
            f"wrote {len(rows)} agent reaction(s) across {len(seg_rows)} segment(s) to memory",
            {"reactions": len(rows), "segments": len(seg_rows)},
        )
        return True
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("write_member_reactions failed: %s", exc)
        record_activity("skipped", "write_member_reactions", source, f"write failed: {exc}")
        return False


# --- read path --------------------------------------------------------------


def _persona_from_record(rec) -> Persona | None:
    try:
        return Persona(
            id=rec.get("member_id") or rec["key"],
            name=rec.get("name") or "Listener",
            kind="audience",
            segment=rec.get("segment"),
            age=rec.get("age"),
            gender=rec.get("gender") or None,
            city=rec.get("city") or None,
            genres=list(rec.get("genres") or []),
            traits=list(rec.get("traits") or []),
            temperature=rec.get("temperature"),
            system_prompt=rec.get("system_prompt") or "You are a PocketFM listener.",
        )
    except Exception:  # noqa: BLE001 - skip a malformed member, keep the rest
        return None


async def load_audience_members(
    limit: int | None = None, source: str = "Audience Simulator"
) -> list[Persona]:
    """Load persisted audience members back as Persona objects. Best-effort."""
    driver = get_driver()
    if driver is None:
        return []
    limit = limit or settings.sim_panel_max
    members: list[Persona] = []
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            res = await session.run(
                "MATCH (m:AudienceMember) "
                "RETURN m.key AS key, m.member_id AS member_id, m.name AS name, "
                "  m.segment AS segment, m.age AS age, m.gender AS gender, "
                "  m.city AS city, m.genres AS genres, m.traits AS traits, "
                "  m.system_prompt AS system_prompt, m.temperature AS temperature "
                "LIMIT $limit",
                limit=limit,
            )
            async for rec in res:
                p = _persona_from_record(rec)
                if p is not None:
                    members.append(p)
        if members:
            record_activity(
                "read",
                "load_audience_members",
                source,
                f"loaded {len(members)} persisted audience member(s) from the graph",
                {"members": len(members)},
            )
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("load_audience_members failed: %s", exc)
    return members


async def count_audience_members() -> int:
    """Number of persisted audience members (0 when graph unavailable)."""
    driver = get_driver()
    if driver is None:
        return 0
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            rec = await (await session.run("MATCH (m:AudienceMember) RETURN count(m) AS c")).single()
            return int(rec["c"]) if rec else 0
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("count_audience_members failed: %s", exc)
        return 0


async def recall_member_memory(member_id: str, limit: int = 4) -> list[dict]:
    """Return a member's most recent past reactions (their memory).

    Used by the agentic loop's 'recall' step so an agent reacts as a returning
    listener who remembers earlier posts. Best-effort; empty on any failure.
    """
    driver = get_driver()
    if driver is None:
        return []
    key = f"AudienceMember:{_slug(member_id)}"
    out: list[dict] = []
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            res = await session.run(
                "MATCH (m:AudienceMember {key:$k})-[r:REACTED_TO]->(p:Post) "
                "RETURN p.name AS post, r.sentiment AS sentiment, "
                "  r.engagement AS engagement, r.comment AS comment, "
                "  r.hook_score AS hook_score, r.will_listen AS will_listen, "
                "  coalesce(r.created,0) AS created "
                "ORDER BY created DESC LIMIT $limit",
                k=key,
                limit=limit,
            )
            async for rec in res:
                out.append(
                    {
                        "post": rec.get("post"),
                        "sentiment": rec.get("sentiment"),
                        "engagement": rec.get("engagement"),
                        "comment": rec.get("comment"),
                        "hook_score": rec.get("hook_score"),
                        "will_listen": rec.get("will_listen"),
                        "created": rec.get("created"),
                    }
                )
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("recall_member_memory failed: %s", exc)
    return out


def _member_filter_clause(
    q, segment, city, gender, genres, age_min, age_max, has_memory
) -> tuple[str, dict]:
    """Build a shared WHERE fragment + params for the Agent Directory queries."""
    clauses: list[str] = []
    params: dict = {}
    if q:
        clauses.append(
            "(toLower(m.name) CONTAINS toLower($q) "
            "OR toLower(coalesce(m.segment,'')) CONTAINS toLower($q) "
            "OR toLower(coalesce(m.city,'')) CONTAINS toLower($q))"
        )
        params["q"] = q
    if segment:
        clauses.append("toLower(coalesce(m.segment,'')) = toLower($segment)")
        params["segment"] = segment
    if city:
        clauses.append("toLower(coalesce(m.city,'')) = toLower($city)")
        params["city"] = city
    if gender:
        clauses.append("toLower(coalesce(m.gender,'')) = toLower($gender)")
        params["gender"] = gender
    if genres:
        clauses.append("any(g IN $genres WHERE g IN coalesce(m.genres, []))")
        params["genres"] = list(genres)
    if age_min is not None:
        clauses.append("m.age IS NOT NULL AND m.age >= $age_min")
        params["age_min"] = age_min
    if age_max is not None:
        clauses.append("m.age IS NOT NULL AND m.age <= $age_max")
        params["age_max"] = age_max
    if has_memory is not None:
        clauses.append("(EXISTS { MATCH (m)-[:REACTED_TO]->(:Post) } = $has_memory)")
        params["has_memory"] = bool(has_memory)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


async def load_audience_members_page(
    *,
    limit: int = 48,
    offset: int = 0,
    q: str | None = None,
    segment: str | None = None,
    city: str | None = None,
    gender: str | None = None,
    genres: list[str] | None = None,
    age_min: int | None = None,
    age_max: int | None = None,
    has_memory: bool | None = None,
    source: str = "Agent Directory",
) -> list[dict]:
    """One filtered, sorted, paginated page of audience agents (+ memory_count)."""
    driver = get_driver()
    if driver is None:
        return []
    where, params = _member_filter_clause(
        q, segment, city, gender, genres, age_min, age_max, has_memory
    )
    params.update({"limit": int(limit), "offset": int(offset)})
    out: list[dict] = []
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            res = await session.run(
                f"MATCH (m:AudienceMember) {where} "
                "OPTIONAL MATCH (m)-[rr:REACTED_TO]->(:Post) "
                "WITH m, count(rr) AS memory_count "
                "RETURN m.key AS key, m.member_id AS member_id, m.name AS name, "
                "  m.segment AS segment, m.age AS age, m.gender AS gender, "
                "  m.city AS city, m.genres AS genres, m.traits AS traits, "
                "  m.temperature AS temperature, memory_count "
                "ORDER BY toLower(coalesce(m.name,'')), m.member_id "
                "SKIP $offset LIMIT $limit",
                **params,
            )
            async for rec in res:
                mc = int(rec.get("memory_count") or 0)
                out.append(
                    {
                        "id": rec.get("member_id") or rec["key"],
                        "name": rec.get("name") or "Listener",
                        "kind": "audience",
                        "segment": rec.get("segment") or "General",
                        "age": rec.get("age"),
                        "gender": rec.get("gender") or "",
                        "city": rec.get("city") or "",
                        "genres": list(rec.get("genres") or []),
                        "traits": list(rec.get("traits") or []),
                        "temperature": rec.get("temperature"),
                        "memory_count": mc,
                        "has_memory": mc > 0,
                    }
                )
        record_activity(
            "read",
            "load_audience_members_page",
            source,
            f"listed {len(out)} audience agent(s) for the directory",
            {"members": len(out)},
        )
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("load_audience_members_page failed: %s", exc)
    return out


async def count_audience_members_filtered(
    *,
    q: str | None = None,
    segment: str | None = None,
    city: str | None = None,
    gender: str | None = None,
    genres: list[str] | None = None,
    age_min: int | None = None,
    age_max: int | None = None,
    has_memory: bool | None = None,
) -> int:
    """True total matching the same filters (page-independent)."""
    driver = get_driver()
    if driver is None:
        return 0
    where, params = _member_filter_clause(
        q, segment, city, gender, genres, age_min, age_max, has_memory
    )
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            rec = await (
                await session.run(
                    f"MATCH (m:AudienceMember) {where} RETURN count(m) AS c", **params
                )
            ).single()
            return int(rec["c"]) if rec else 0
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("count_audience_members_filtered failed: %s", exc)
        return 0


async def get_audience_member(member_id: str) -> Persona | None:
    """Load one audience agent's full profile (incl. system prompt)."""
    driver = get_driver()
    if driver is None:
        return None
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            rec = await (
                await session.run(
                    "MATCH (m:AudienceMember) WHERE m.member_id=$id OR m.key=$key "
                    "RETURN m.key AS key, m.member_id AS member_id, m.name AS name, "
                    "  m.segment AS segment, m.age AS age, m.gender AS gender, "
                    "  m.city AS city, m.genres AS genres, m.traits AS traits, "
                    "  m.system_prompt AS system_prompt, m.temperature AS temperature LIMIT 1",
                    id=member_id,
                    key=f"AudienceMember:{_slug(member_id)}",
                )
            ).single()
            return _persona_from_record(rec) if rec else None
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("get_audience_member failed: %s", exc)
        return None


async def audience_facets() -> dict:
    """Distinct filter values (segment / city / gender / genre) with counts."""
    out: dict = {"segments": [], "cities": [], "genders": [], "genres": [], "total": 0}
    driver = get_driver()
    if driver is None:
        return out
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            total = await (
                await session.run("MATCH (m:AudienceMember) RETURN count(m) AS c")
            ).single()
            out["total"] = int(total["c"]) if total else 0
            for field, key in (("segment", "segments"), ("city", "cities"), ("gender", "genders")):
                res = await session.run(
                    f"MATCH (m:AudienceMember) WITH coalesce(m.{field},'') AS v "
                    "WHERE v <> '' RETURN v, count(*) AS c ORDER BY c DESC LIMIT 60"
                )
                out[key] = [{"value": r["v"], "count": int(r["c"])} async for r in res]
            gres = await session.run(
                "MATCH (m:AudienceMember) UNWIND coalesce(m.genres,[]) AS g "
                "WITH g WHERE g <> '' RETURN g AS v, count(*) AS c ORDER BY c DESC LIMIT 60"
            )
            out["genres"] = [{"value": r["v"], "count": int(r["c"])} async for r in gres]
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("audience_facets failed: %s", exc)
    return out


# --- mutation path (agent edit / create / memory reset) ---------------------
# These make each agent WRITE-addressable: edit a profile in place, spawn a new
# listener, or clear one agent's memory. Identity (key/member_id) is immutable
# on edit so the agent's REACTED_TO history stays attached.


async def update_audience_member(
    member_id: str,
    *,
    name: str | None = None,
    segment: str | None = None,
    age: int | None = None,
    gender: str | None = None,
    city: str | None = None,
    genres: list[str] | None = None,
    traits: list[str] | None = None,
    system_prompt: str | None = None,
    temperature: float | None = None,
    source: str = "Agent API",
) -> Persona | None:
    """Update an existing agent's mutable profile fields in place.

    Only the fields passed (non-None) are changed. Identity (``key``/
    ``member_id``) is never touched, so the agent keeps its memory (its
    ``REACTED_TO`` edges). When ``segment`` changes, the ``BELONGS_TO`` cohort
    edge is re-linked so the graph view stays consistent. Returns the refreshed
    Persona, or None if the agent doesn't exist / the graph is unavailable.
    """
    driver = get_driver()
    if driver is None:
        return None
    updates = {
        "name": name,
        "segment": segment,
        "age": age,
        "gender": gender,
        "city": city,
        "genres": list(genres) if genres is not None else None,
        "traits": list(traits) if traits is not None else None,
        "system_prompt": system_prompt,
        "temperature": temperature,
    }
    updates = {k: v for k, v in updates.items() if v is not None}
    key = f"AudienceMember:{_slug(member_id)}"
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            # MATCH (never MERGE) so a bad id can't silently create a ghost node.
            found = await (
                await session.run(
                    "MATCH (m:AudienceMember) WHERE m.member_id=$id OR m.key=$key "
                    "RETURN m.key AS key LIMIT 1",
                    id=member_id,
                    key=key,
                )
            ).single()
            if not found:
                return None
            node_key = found["key"]
            if updates:
                set_parts = ", ".join(f"m.{f} = ${f}" for f in updates)
                await session.run(
                    f"MATCH (m:AudienceMember {{key:$node_key}}) SET {set_parts}",
                    node_key=node_key,
                    **updates,
                )
            if "segment" in updates:
                # Keep the cohort edge + segment node in sync with the property.
                await session.run(
                    "MATCH (m:AudienceMember {key:$node_key}) "
                    "OPTIONAL MATCH (m)-[b:BELONGS_TO]->(:AudienceSegment) DELETE b "
                    "WITH m "
                    "MERGE (s:Canon:AudienceSegment {key:$seg_key}) "
                    "SET s.type='AudienceSegment', s.name=$segment "
                    "MERGE (m)-[:BELONGS_TO]->(s)",
                    node_key=node_key,
                    seg_key=_segment_key(updates["segment"]),
                    segment=updates["segment"],
                )
        record_activity(
            "write",
            "update_audience_member",
            source,
            f"edited agent '{member_id}': {', '.join(updates) or 'no fields'}",
            {"fields": list(updates)},
        )
        return await get_audience_member(member_id)
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("update_audience_member failed: %s", exc)
        record_activity("skipped", "update_audience_member", source, f"edit failed: {exc}")
        return None


async def create_audience_member(
    *,
    name: str,
    segment: str | None = None,
    age: int | None = None,
    gender: str | None = None,
    city: str | None = None,
    genres: list[str] | None = None,
    traits: list[str] | None = None,
    system_prompt: str | None = None,
    temperature: float | None = None,
    source: str = "Agent API",
) -> Persona | None:
    """Create a brand-new listener agent and persist it. Returns the Persona.

    A usable persona prompt is generated from the traits/genres/city when
    ``system_prompt`` is omitted, so the new agent can react in character.
    """
    agent_id = f"aud-{uuid4().hex}"
    if not system_prompt:
        head = f"You are {name}, a PocketFM listener"
        if city:
            head += f" from {city}"
        if segment:
            head += f" in the {segment} audience"
        parts = [head + "."]
        if genres:
            parts.append("You mostly enjoy " + ", ".join(genres) + ".")
        if traits:
            parts.append("You are " + ", ".join(traits) + ".")
        parts.append("React to teasers honestly, in your own voice.")
        system_prompt = " ".join(parts)
    persona = Persona(
        id=agent_id,
        name=name,
        kind="audience",
        segment=segment,
        age=age,
        gender=gender,
        city=city,
        genres=list(genres or []),
        traits=list(traits or []),
        temperature=temperature,
        system_prompt=system_prompt,
    )
    written = await save_audience_members([persona], source=source)
    if not written:
        return None
    return await get_audience_member(agent_id)


async def reset_member_memory(member_id: str, source: str = "Agent API") -> int:
    """Delete one agent's reaction history (its ``REACTED_TO`` edges).

    Only that agent's memory edges are removed; the agent node and the shared
    Post nodes stay. Returns the number of reactions cleared (0 if none / the
    agent is missing / the graph is unavailable).
    """
    driver = get_driver()
    if driver is None:
        return 0
    key = f"AudienceMember:{_slug(member_id)}"
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            rec = await (
                await session.run(
                    "MATCH (m:AudienceMember) WHERE m.member_id=$id OR m.key=$key "
                    "OPTIONAL MATCH (m)-[r:REACTED_TO]->(:Post) "
                    "WITH collect(r) AS rs "
                    "FOREACH (x IN rs | DELETE x) "
                    "RETURN size(rs) AS n",
                    id=member_id,
                    key=key,
                )
            ).single()
            deleted = int(rec["n"]) if rec else 0
        if deleted:
            record_activity(
                "write",
                "reset_member_memory",
                source,
                f"cleared {deleted} reaction(s) from agent '{member_id}'",
                {"forgotten": deleted},
            )
        return deleted
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("reset_member_memory failed: %s", exc)
        return 0


async def recall_members_memories(
    member_ids: list[str],
    limit: int = 4,
    show: str = "",
    source: str = "Cliffhanger Planner",
) -> dict[str, list[dict]]:
    """Batch-load a frozen memory snapshot for a listener cohort.

    The planner compares multiple endings. Reading every member once prevents
    N+1 graph queries and, more importantly, guarantees that the original and
    every candidate see the exact same prior history. New reactions are written
    only after scoring has completed.
    """
    driver = get_driver()
    if driver is None or not member_ids:
        return {}
    out: dict[str, list[dict]] = {member_id: [] for member_id in member_ids}
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            res = await session.run(
                "UNWIND $ids AS member_id "
                "OPTIONAL MATCH (m:AudienceMember {member_id:member_id}) "
                "CALL (m) { "
                "  OPTIONAL MATCH (m)-[r:REACTED_TO]->(p:Post) "
                "  WHERE $show = '' OR p.show = $show OR p.name = $show "
                "  WITH p, r ORDER BY coalesce(r.created,0) DESC LIMIT $limit "
                "  RETURN collect({post:p.name, sentiment:r.sentiment, "
                "    engagement:r.engagement, comment:r.comment}) AS items "
                "} "
                "RETURN member_id, items",
                ids=member_ids,
                limit=limit,
                show=show,
            )
            async for rec in res:
                items = [
                    dict(item)
                    for item in (rec.get("items") or [])
                    if item and item.get("post")
                ]
                out[str(rec["member_id"])] = items
        hits = sum(1 for items in out.values() if items)
        record_activity(
            "read",
            "recall_members_memories",
            source,
            f"recalled personal history for {hits} of {len(member_ids)} audience members",
            {"members": len(member_ids), "memory_hits": hits},
        )
    except Exception as exc:  # noqa: BLE001 - graph memory is best-effort
        logger.warning("recall_members_memories failed: %s", exc)
        record_activity(
            "skipped",
            "recall_members_memories",
            source,
            f"batch recall failed: {exc}",
        )
    return out


async def write_cliffhanger_evaluations(
    story: Story,
    original_text: str,
    winner_text: str,
    original_pairs: list[tuple[Persona, CliffhangerRating]],
    winner_pairs: list[tuple[Persona, CliffhangerRating]],
    source: str = "Cliffhanger Planner",
) -> int:
    """Persist an unpublished experiment without polluting listener history.

    ``EVALUATED_IN`` edges are proof that persistent identities participated,
    but ``recall_member_memory`` intentionally reads only ``REACTED_TO`` edges.
    This prevents a future agent from remembering a candidate that no listener
    actually heard in production. Returns the exact number of matched edges.
    """
    driver = get_driver()
    if driver is None or not winner_pairs:
        record_activity(
            "skipped",
            "write_cliffhanger_evaluations",
            source,
            "graph disabled — experiment was not persisted",
        )
        return 0
    experiment_key = (
        f"CliffhangerExperiment:{_slug(story.title or 'untitled')}-{uuid4().hex}"
    )
    original_by_member = {
        member.id: rating for member, rating in original_pairs
    }
    rows = [
        {
            "member_key": _member_key(member),
            "original_hook_score": original_by_member[member.id].hook_score,
            "original_will_continue": original_by_member[member.id].will_continue,
            "original_reason": original_by_member[member.id].reason[:500],
            "winner_hook_score": winner_rating.hook_score,
            "winner_will_continue": winner_rating.will_continue,
            "winner_reason": winner_rating.reason[:500],
            "lift": winner_rating.hook_score - original_by_member[member.id].hook_score,
        }
        for member, winner_rating in winner_pairs
        if member.id in original_by_member
    ]
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            result = await session.run(
                "MERGE (x:CliffhangerExperiment {key:$key}) "
                "SET x.show=$show, x.episode=$episode, x.original_text=$original, "
                "  x.winner_text=$winner, x.created=$created "
                "WITH x "
                "UNWIND $rows AS row "
                "MATCH (m:AudienceMember {key:row.member_key}) "
                "MERGE (m)-[r:EVALUATED_IN {experiment_key:$key}]->(x) "
                "SET r.original_hook_score=row.original_hook_score, "
                "  r.original_will_continue=row.original_will_continue, "
                "  r.original_reason=row.original_reason, "
                "  r.winner_hook_score=row.winner_hook_score, "
                "  r.winner_will_continue=row.winner_will_continue, "
                "  r.winner_reason=row.winner_reason, r.lift=row.lift, "
                "  r.created=$created "
                "RETURN count(r) AS written",
                key=experiment_key,
                show=story.title,
                episode=story.episode or "",
                original=original_text[:2000],
                winner=winner_text[:2000],
                created=time.time(),
                rows=rows,
            )
            record = await result.single()
            written = int(record["written"]) if record else 0
        op = "write" if written == len(rows) else "skipped"
        record_activity(
            op,
            "write_cliffhanger_evaluations",
            source,
            f"persisted {written} of {len(rows)} winner evaluation(s) to experiment memory",
            {"evaluations": written, "expected": len(rows)},
        )
        return written
    except Exception as exc:  # noqa: BLE001 - graph memory is best-effort
        logger.warning("write_cliffhanger_evaluations failed: %s", exc)
        record_activity(
            "skipped",
            "write_cliffhanger_evaluations",
            source,
            f"experiment write failed: {exc}",
        )
        return 0
