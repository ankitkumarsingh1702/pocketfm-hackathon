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
                    }
                )
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("recall_member_memory failed: %s", exc)
    return out


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
