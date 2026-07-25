#!/usr/bin/env python
"""Seed a large, coherent ANDHERA show canon into the Neo4j knowledge graph.

Why this exists
---------------
The Plot Hole Hunter's promise is to "reason across thousands of pages." With
only one or two ingested episodes the graph is tiny, so the capability isn't
visible. This script populates a realistic ~50-episode / ~2,200-fact canon for
the ANDHERA horror serial, with a handful of DELIBERATE cross-episode
contradictions planted far apart — the exact thing a human can't catch by
re-reading the whole show, but the graph traversal finds instantly.

Design guarantees
-----------------
* Deterministic + idempotent: fixed keys (byte-identical to the real ingest
  path via ``app.graph.store._slug``), so re-running MERGEs to the same graph.
* Conflict-proof by construction: two disjoint fact families —
  (a) episode-scoped event facts (predicate ``ep{n}_event_{i}`` is unique per
      episode+index, so they can NEVER collide), and
  (b) stable "bible" facts, where each (subject, predicate) maps to exactly one
      object (a build-time assertion enforces this).
  The ONLY same-(subject,predicate)-different-object collisions are the 4
  planted hero contradictions.
* Every seeded node carries ``seed_batch='andhera-v1'``. ``--reset`` deletes only
  that batch; ``--wipe`` clears the whole canon for a truly fresh slate.

Run it (creds come from backend/.env, so run from backend/):

    cd backend
    uv run python ../scripts/seed_canon.py --wipe --yes
"""

from __future__ import annotations

import argparse
import pathlib
import sys

# Make ``app.*`` importable when run from anywhere (creds load from backend/.env).
_BACKEND = pathlib.Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from neo4j import GraphDatabase  # noqa: E402

from app.config import settings  # noqa: E402
from app.graph.store import _node_id, _slug  # noqa: E402

SEED_BATCH = "andhera-v1"
SHOW_TITLE = "ANDHERA"
N_EPISODES = 50
EVENTS_PER_EPISODE = 44          # 50 * 44 = 2,200 episode-scoped event facts
PAGES_PER_EPISODE = 40           # keep in sync with backend _PAGES_PER_EPISODE

# ---------------------------------------------------------------------------
# Story bible — entities (consistent with data/sample_stories/andhera_ep7.md)
# ---------------------------------------------------------------------------

CHARACTERS = [
    ("Naina", "Journalist who moves into Shanti Kunj and investigates the sixth floor."),
    ("Rohan", "Naina's closest friend; the steady voice on the other end of the phone."),
    ("Mr. Kulkarni", "Society secretary who insists the sixth floor never existed."),
    ("Mrs. Dsouza", "Third-floor resident who repeats the same warning at the milk booth."),
    ("The Girl", "The child heard in flat 6B — 'You found us. Nobody finds us.'"),
    ("Ananya", "Naina's younger sister, whose loss drives Naina's obsession."),
    ("Vikram", "The father of the family that lived in 6B before 1998."),
    ("Sunita", "The mother of the 6B family; folded her saris very neatly."),
    ("Ramu Kaka", "The building's old watchman who has seen every resident come and go."),
    ("Inspector Deshmukh", "Investigated the 1998 fire; the file was quietly closed."),
    ("Priya", "Naina's colleague at the paper who helps her dig into archives."),
    ("Dr. Sen", "A psychiatrist Rohan urges Naina to see."),
    ("Mr. Fernandes", "The oldest resident, who remembers the building before the fire."),
    ("Kavya", "A teenager on the fourth floor who also hears the lullaby."),
    ("The Landlord", "Owns Shanti Kunj and refuses to discuss flat 6B."),
    (" Meena", "The society's cleaner who avoids the sixth-floor button."),
    ("Arjun", "Naina's editor, skeptical of the whole story."),
    ("Constable Pawar", "Deshmukh's junior, who kept a private note about the fire."),
]

LOCATIONS = [
    ("The apartment building", "Shanti Kunj — the building at the centre of it all."),
    ("Flat 6B", "The flat on the floor that supposedly doesn't exist."),
    ("The lift", "It sometimes rises to a sixth floor and stops on its own."),
    ("The sixth floor", "Chhati manzil — a corridor that shouldn't be there."),
    ("The terrace", "Where an old child's swing still creaks in no wind."),
    ("The milk booth", "Where Mrs. Dsouza repeats her warning every morning."),
    ("Flat 2A", "Naina's own flat, two floors below the mystery."),
    ("The society office", "Where the register lists 6B as sealed."),
    ("The basement", "Damp, forgotten, and colder than it should be."),
    ("The staircase", "Its landing camera catches things that aren't there."),
    ("Flat 3C", "Mrs. Dsouza's flat on the third floor."),
    ("The watchman's cabin", "Ramu Kaka's post by the gate."),
    ("The old well", "Behind the building, boarded over since the fire."),
    ("The archive room", "Where Priya and Naina read the 1998 clippings."),
]

PLOT_THREADS = [
    ("The sixth-floor mystery", "Does the sixth floor exist, and who is up there?"),
    ("The 1998 fire", "What really happened the night flat 6B burned?"),
    ("The chalk word", "Who keeps writing 'ANDHERA' in every room?"),
    ("Naina's diary", "Her record of the haunting, three pages and growing."),
    ("The girl's identity", "Who is the child, and why does no one remember her?"),
    ("The sealed flat", "Why 6B was sealed, and by whose order."),
    ("Ananya's death", "The loss Naina is really running from."),
    ("The society's silence", "Why every resident tells the same rehearsed story."),
    ("The missing family", "What became of Vikram, Sunita, and their daughter."),
    ("The lift's will", "Why the lift chooses the sixth floor on its own."),
    ("The closed file", "Why Inspector Deshmukh's fire report was buried."),
    ("The lullaby", "The tune heard in 6B that others start to hum."),
]

CLUES = [
    ("The 1998 calendar", "A calendar in 6B stopped at June 1998."),
    ("The neatly folded saris", "Someone left the cupboard perfectly kept."),
    ("The dry tap", "The kitchen tap runs, then gives nothing."),
    ("The powerless fan", "A ceiling fan that turns with no electricity."),
    ("The batteryless clock", "A clock that ticks with no batteries."),
    ("The register entry", "6B: 'sealed since the fire of 1998.'"),
    ("The sixth-floor button", "It lights up in the lift on its own."),
    ("The child's laughter", "A laugh far down the corridor, then swallowed."),
    ("The erased writing", "The chalk word rubbed out from inside the wall."),
    ("The burnt diary page", "A charred page that doesn't match Naina's diary."),
    ("The impossible key", "A key to 6B that the office says was never cut."),
    ("The school uniform", "A child's uniform folded in the 6B cupboard."),
    ("The scratched name", "A name gouged under the paint by the door."),
    ("The broken swing", "The terrace swing creaks against still air."),
    ("The wet footprints", "Small, wet footprints leading to the lift."),
    ("The locket", "A locket with a photo too faded to read."),
    ("The fire clipping", "A 1998 newspaper clipping about the blaze."),
    ("The phone recording", "A lullaby captured on Naina's dead phone."),
    ("The chalk word", "'ANDHERA' rewritten in chalk in every room."),          # DANGLING
    ("The face-down photograph", "A family photo left face-down in 6B."),        # DANGLING
]
# The last two clues are intentionally left with no payoff edge (dangling).
DANGLING_CLUES = {"The chalk word", "The face-down photograph"}

THEMES = [
    ("Grief", "Loss that refuses to be put down."),
    ("Memory versus denial", "A community that chooses to forget."),
    ("The buried past", "What is sealed away does not stay sealed."),
    ("Motherhood", "A mother's love outlasting the fire."),
    ("Guilt", "The thin line between a haunting and a conscience."),
    ("Silence", "The things everyone agrees not to say."),
]

# ---------------------------------------------------------------------------
# Hero contradictions — the whole demo. Same (subject, predicate), two objects,
# planted far apart. Each row: (entity_type, entity_name, predicate, obj, epnum).
# ---------------------------------------------------------------------------

HERO_CONFLICTS = [
    ("Location", "The apartment building", "floor_count", "5", 1),
    ("Location", "The apartment building", "floor_count", "6", 33),
    ("Location", "Flat 6B", "status", "sealed since the fire of 1998", 4),
    ("Location", "Flat 6B", "status", "occupied by a young couple", 41),
    ("Character", "The Girl", "death_year", "1998", 7),
    ("Character", "The Girl", "death_year", "2003", 46),
    ("Character", "Rohan", "whereabouts_1998", "in the building as a child", 2),
    ("Character", "Rohan", "whereabouts_1998", "abroad in London until 2001", 38),
]

# ---------------------------------------------------------------------------
# Stable "bible" facts — one object per (subject, predicate). Avoid every
# (subject, predicate) used by HERO_CONFLICTS. (type, name, predicate, object)
# ---------------------------------------------------------------------------

STABLE_FACTS = [
    ("Location", "The apartment building", "name", "Shanti Kunj"),
    ("Location", "The apartment building", "built_year", "1994"),
    ("Location", "The apartment building", "official_address", "Shanti Kunj, Dadar"),
    ("Location", "Flat 6B", "on_floor", "the sixth floor"),
    ("Location", "Flat 6B", "sealed_by", "the society, by order of the landlord"),
    ("Location", "The lift", "quirk", "rises to the sixth floor on its own"),
    ("Location", "The sixth floor", "exists_officially", "no"),
    ("Location", "The terrace", "feature", "an old child's swing"),
    ("Location", "The old well", "state", "boarded over since 1998"),
    ("Character", "Naina", "role", "journalist and investigator"),
    ("Character", "Naina", "lives_in", "Flat 2A"),
    ("Character", "Naina", "keeps", "a diary of the haunting"),
    ("Character", "Naina", "motive", "her sister Ananya's death"),
    ("Character", "Rohan", "role", "Naina's friend and phone anchor"),
    ("Character", "Rohan", "relation_to_naina", "closest friend"),
    ("Character", "Mr. Kulkarni", "role", "society secretary"),
    ("Character", "Mr. Kulkarni", "stance", "insists the sixth floor never existed"),
    ("Character", "Mrs. Dsouza", "lives_on", "the third floor"),
    ("Character", "Mrs. Dsouza", "habit", "repeats the warning at the milk booth"),
    ("Character", "The Girl", "first_line_spoken", "You found us. Nobody finds us."),
    ("Character", "The Girl", "lived_in", "Flat 6B"),
    ("Character", "Ananya", "relation_to_naina", "younger sister"),
    ("Character", "Ananya", "status", "died three years ago"),
    ("Character", "Vikram", "role", "father of the 6B family"),
    ("Character", "Sunita", "role", "mother of the 6B family"),
    ("Character", "Sunita", "detail", "folded her saris very neatly"),
    ("Character", "Ramu Kaka", "role", "the building watchman"),
    ("Character", "Inspector Deshmukh", "role", "investigated the 1998 fire"),
    ("Character", "Inspector Deshmukh", "outcome", "the file was quietly closed"),
    ("Character", "Priya", "role", "Naina's colleague at the paper"),
    ("Character", "Dr. Sen", "role", "psychiatrist Rohan recommends"),
    ("Character", "Mr. Fernandes", "role", "oldest resident of Shanti Kunj"),
    ("Character", "Kavya", "detail", "also hears the lullaby"),
    ("Character", "Constable Pawar", "detail", "kept a private note on the fire"),
    ("PlotThread", "The 1998 fire", "year", "1998"),
    ("PlotThread", "The 1998 fire", "location", "the sixth floor of Shanti Kunj"),
    ("PlotThread", "Naina's diary", "current_length", "three pages"),
    ("PlotThread", "The chalk word", "word", "ANDHERA"),
    ("PlotThread", "The girl's identity", "clue", "no resident remembers the child"),
    ("PlotThread", "The lullaby", "heard_in", "flat 6B"),
    ("Clue", "The 1998 calendar", "stopped_at", "June 1998"),
    ("Clue", "The register entry", "reads", "sealed since the fire of 1998"),
    ("Clue", "The sixth-floor button", "behaviour", "lights up on its own"),
    ("Clue", "The fire clipping", "dated", "1998"),
    ("Clue", "The impossible key", "office_says", "never cut"),
    ("Clue", "The school uniform", "found_in", "the 6B cupboard"),
]

# ---------------------------------------------------------------------------
# Episode titles
# ---------------------------------------------------------------------------

EPISODE_TITLES = [
    "The Knock", "The Register", "The Milk Booth", "Sealed", "The Warning",
    "The Lullaby", "Chhati Manzil", "The Folded Saris", "The Dry Tap", "The Swing",
    "The Photograph", "The Impossible Key", "The Archive", "The Closed File", "The Well",
    "The Uniform", "The Locket", "The Fourth Floor", "The Editor", "The Recording",
    "The Cold Corridor", "The Face at the Glass", "The Neighbour", "The Constable's Note",
    "The Burnt Page", "The Empty Cradle", "The Landlord", "The Séance", "The Old Resident",
    "The Second Fire", "The Name Under Paint", "The Watchman's Tale", "Six Floors",
    "The Erased Wall", "The Return", "The Diary Grows", "The Missing Photograph",
    "London", "The Confession", "The Sealed Door Opens", "A Young Couple", "The Basement",
    "The Lift Descends", "The Society Meeting", "The Reckoning", "Two Thousand Three",
    "The Last Warning", "The Chalk Fades", "What the Fire Left", "Nobody Finds Us",
]

# ---------------------------------------------------------------------------
# Event-fact beat templates (the volume). {name} = subject, {n} = episode number.
# ---------------------------------------------------------------------------

TEMPLATES = [
    "{name} surfaces again as the sixth-floor cold returns on night {n}.",
    "Naina records {name} in her diary during episode {n}.",
    "The lift pauses when {name} is near, in episode {n}.",
    "{name} is tied to the 1998 fire by a detail found in episode {n}.",
    "A neighbour mentions {name}, then falls silent, in episode {n}.",
    "Rohan warns Naina about {name} over the phone in episode {n}.",
    "The chalk word is found beside {name} in episode {n}.",
    "{name} recurs in Naina's phone recording from episode {n}.",
    "Mr. Kulkarni deflects every question about {name} in episode {n}.",
    "{name} leads Naina back to flat 6B in episode {n}.",
    "A photograph shows {name} in the background in episode {n}.",
    "{name} feels colder to the touch this night, episode {n}.",
    "The register has a struck-out line about {name}, episode {n}.",
    "{name} appears on the stairwell camera in episode {n}.",
    "Naina nearly leaves, then {name} pulls her back, episode {n}.",
    "{name} hums the lullaby first heard in 6B, episode {n}.",
    "Priya digs up an archive note on {name} in episode {n}.",
    "{name} goes quiet the moment the lift doors open, episode {n}.",
]


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _ep_key(n: int) -> str:
    return f"Episode:{_slug(SHOW_TITLE, f'Episode {n}')}"


def _fact_row(subject_key: str, predicate: str, obj: str, ep_key: str) -> dict:
    return {
        "key": f"Fact:{_slug(subject_key, predicate, obj)}",
        "subject_key": subject_key,
        "predicate": predicate,
        "object": obj,
        "ep": ep_key,
    }


def build_episodes() -> list[dict]:
    rows = []
    for n in range(1, N_EPISODES + 1):
        title = EPISODE_TITLES[(n - 1) % len(EPISODE_TITLES)]
        rows.append(
            {
                "key": _ep_key(n),
                "name": f"{SHOW_TITLE} — Episode {n}: {title}",
                "title": SHOW_TITLE,
                "episode": f"Episode {n}",
                "epnum": n,
            }
        )
    return rows


def build_entities() -> dict[str, list[dict]]:
    """Typed entity rows keyed by node type. Home episode = 1 for connectivity."""
    ep1 = _ep_key(1)
    out: dict[str, list[dict]] = {}
    for etype, items in (
        ("Character", CHARACTERS),
        ("Location", LOCATIONS),
        ("PlotThread", PLOT_THREADS),
        ("Clue", CLUES),
        ("Theme", THEMES),
    ):
        rows = []
        for name, desc in items:
            rows.append(
                {"key": _node_id(etype, name), "name": name, "description": desc, "ep": ep1}
            )
        out[etype] = rows
    return out


def build_relations() -> dict[str, list[dict]]:
    """Coherent edges. Every clue EXCEPT the two dangling ones gets an outgoing
    (non-MENTIONED_IN) edge, so only those two register as dangling."""
    rels: dict[str, list[dict]] = {}

    def add(rtype: str, src: str, dst: str, detail: str = "") -> None:
        rels.setdefault(rtype, []).append({"src": src, "dst": dst, "detail": detail})

    C = lambda name: _node_id("Character", name)  # noqa: E731
    L = lambda name: _node_id("Location", name)  # noqa: E731
    P = lambda name: _node_id("PlotThread", name)  # noqa: E731
    K = lambda name: _node_id("Clue", name)  # noqa: E731

    # Characters ↔ threads / locations
    add("INVESTIGATES", C("Naina"), P("The sixth-floor mystery"), "her central obsession")
    add("INVESTIGATES", C("Naina"), P("The 1998 fire"), "digs into the archive")
    add("HAUNTED_BY", C("Naina"), P("Ananya's death"), "the loss she runs from")
    add("LOCATED_AT", C("Naina"), L("Flat 2A"), "lives two floors below")
    add("WARNS", C("Rohan"), C("Naina"), "get out of that lift")
    add("COVERS_UP", C("Mr. Kulkarni"), P("The society's silence"), "insists it never existed")
    add("REPEATS_WARNING", C("Mrs. Dsouza"), P("The society's silence"), "same story every week")
    add("HAUNTS", C("The Girl"), L("Flat 6B"), "the child in 6B")
    add("PART_OF", C("Vikram"), P("The missing family"), "the father")
    add("PART_OF", C("Sunita"), P("The missing family"), "the mother")
    add("PART_OF", C("The Girl"), P("The missing family"), "the daughter")
    add("INVESTIGATED", C("Inspector Deshmukh"), P("The 1998 fire"), "closed file")
    add("KEPT_NOTE", C("Constable Pawar"), P("The closed file"), "a private note")

    # Threads set in locations
    add("SET_IN", P("The sixth-floor mystery"), L("The sixth floor"), "")
    add("SET_IN", P("The 1998 fire"), L("Flat 6B"), "")
    add("SET_IN", P("The lift's will"), L("The lift"), "")
    add("SET_IN", P("The lullaby"), L("Flat 6B"), "")

    # Non-dangling clues → each gets a payoff edge
    payoffs = [
        (K("The 1998 calendar"), P("The 1998 fire")),
        (K("The neatly folded saris"), P("The missing family")),
        (K("The dry tap"), P("The sixth-floor mystery")),
        (K("The powerless fan"), P("The sixth-floor mystery")),
        (K("The batteryless clock"), P("The sixth-floor mystery")),
        (K("The register entry"), P("The sealed flat")),
        (K("The sixth-floor button"), P("The lift's will")),
        (K("The child's laughter"), P("The girl's identity")),
        (K("The erased writing"), P("The chalk word")),
        (K("The burnt diary page"), P("Naina's diary")),
        (K("The impossible key"), P("The sealed flat")),
        (K("The school uniform"), P("The girl's identity")),
        (K("The scratched name"), P("The missing family")),
        (K("The broken swing"), P("The girl's identity")),
        (K("The wet footprints"), P("The lift's will")),
        (K("The locket"), P("The missing family")),
        (K("The fire clipping"), P("The 1998 fire")),
        (K("The phone recording"), P("The lullaby")),
    ]
    for src, dst in payoffs:
        add("FORESHADOWS", src, dst, "pays off later")

    return rels


def build_stable_facts() -> list[dict]:
    """Stable bible facts spread across the early episodes."""
    rows = []
    for i, (etype, name, pred, obj) in enumerate(STABLE_FACTS):
        ep = _ep_key((i % 12) + 1)  # spread across episodes 1-12
        rows.append(_fact_row(_node_id(etype, name), pred, obj, ep))
    return rows


def build_hero_facts() -> list[dict]:
    rows = []
    for etype, name, pred, obj, epnum in HERO_CONFLICTS:
        rows.append(_fact_row(_node_id(etype, name), pred, obj, _ep_key(epnum)))
    return rows


def build_event_facts() -> list[dict]:
    """The volume: EVENTS_PER_EPISODE per episode, episode-scoped predicates so
    they can never accidentally collide."""
    # Subjects for events: characters + locations + non-dangling clues.
    subjects: list[tuple[str, str]] = []
    for name, _ in CHARACTERS:
        subjects.append((_node_id("Character", name), name))
    for name, _ in LOCATIONS:
        subjects.append((_node_id("Location", name), name))
    for name, _ in CLUES:
        if name not in DANGLING_CLUES:
            subjects.append((_node_id("Clue", name), name))

    rows = []
    for n in range(1, N_EPISODES + 1):
        ep = _ep_key(n)
        for i in range(1, EVENTS_PER_EPISODE + 1):
            skey, sname = subjects[(n * 7 + i) % len(subjects)]
            tmpl = TEMPLATES[(n + i) % len(TEMPLATES)]
            obj = tmpl.format(name=sname, n=n)
            predicate = f"ep{n:02d}_event_{i:02d}"
            rows.append(_fact_row(skey, predicate, obj, ep))
    return rows


def assert_no_accidental_conflicts(stable: list[dict], hero: list[dict]) -> None:
    """Guard: no (subject, predicate) among stable facts maps to two objects, and
    no stable fact reuses a hero (subject, predicate)."""
    hero_keys = {(f["subject_key"], f["predicate"]) for f in hero}
    seen: dict[tuple[str, str], str] = {}
    for f in stable:
        k = (f["subject_key"], f["predicate"])
        assert k not in hero_keys, f"stable fact reuses hero predicate: {k}"
        if k in seen:
            assert seen[k] == f["object"], f"accidental conflict at {k}: {seen[k]!r} vs {f['object']!r}"
        seen[k] = f["object"]


# ---------------------------------------------------------------------------
# Write path (sync driver)
# ---------------------------------------------------------------------------

_INDEXES = [
    "CREATE INDEX fact_subject_key IF NOT EXISTS FOR (f:Fact) ON (f.subject_key)",
    "CREATE INDEX fact_predicate IF NOT EXISTS FOR (f:Fact) ON (f.predicate)",
    "CREATE INDEX fact_subj_pred IF NOT EXISTS FOR (f:Fact) ON (f.subject_key, f.predicate)",
    "CREATE INDEX episode_epnum IF NOT EXISTS FOR (e:Episode) ON (e.epnum)",
]

_ALLOWED_LABELS = {"Character", "PlotThread", "Clue", "Location", "Theme"}


def _chunks(rows: list[dict], size: int = 500):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def write_episodes(session, rows: list[dict]) -> None:
    for chunk in _chunks(rows):
        session.run(
            "UNWIND $rows AS row "
            "MERGE (e:Canon:Episode {key: row.key}) "
            "SET e.type='Episode', e.name=row.name, e.title=row.title, "
            "e.episode=row.episode, e.epnum=row.epnum, e.seed_batch=$batch",
            rows=chunk, batch=SEED_BATCH,
        )


def write_entities(session, by_type: dict[str, list[dict]]) -> None:
    for etype, rows in by_type.items():
        label = etype if etype in _ALLOWED_LABELS else "Entity"
        for chunk in _chunks(rows):
            session.run(
                "UNWIND $rows AS row "
                "MERGE (n:Canon {key: row.key}) "
                f"SET n:{label}, n.type=$etype, n.name=row.name, "
                "n.description=row.description, n.seed_batch=$batch "
                "WITH n, row MATCH (e:Canon:Episode {key: row.ep}) "
                "MERGE (n)-[:MENTIONED_IN]->(e)",
                rows=chunk, etype=etype, batch=SEED_BATCH,
            )


def write_relations(session, by_type: dict[str, list[dict]]) -> None:
    for rtype, rows in by_type.items():
        for chunk in _chunks(rows):
            session.run(
                "UNWIND $rows AS row "
                "MATCH (a:Canon {key: row.src}), (b:Canon {key: row.dst}) "
                f"MERGE (a)-[r:{rtype}]->(b) SET r.detail = row.detail",
                rows=chunk,
            )


def write_facts(session, rows: list[dict]) -> None:
    for chunk in _chunks(rows):
        session.run(
            "UNWIND $rows AS row "
            "MERGE (f:Canon:Fact {key: row.key}) "
            "SET f.type='Fact', f.name=row.predicate, f.subject_key=row.subject_key, "
            "f.predicate=row.predicate, f.object=row.object, f.seed_batch=$batch "
            "WITH f, row MATCH (e:Canon:Episode {key: row.ep}) "
            "MERGE (f)-[:IN_EPISODE]->(e) "
            "WITH f, row OPTIONAL MATCH (s:Canon {key: row.subject_key}) "
            "FOREACH (_ IN CASE WHEN s IS NULL THEN [] ELSE [1] END | "
            "MERGE (s)-[:ASSERTS]->(f))",
            rows=chunk, batch=SEED_BATCH,
        )


def write_indexes(session) -> None:
    for stmt in _INDEXES:
        session.run(stmt)


def reset_batch(session) -> int:
    rec = session.run(
        "MATCH (n:Canon {seed_batch: $batch}) DETACH DELETE n RETURN count(n) AS c",
        batch=SEED_BATCH,
    ).single()
    return rec["c"] if rec else 0


def wipe_all(session) -> int:
    rec = session.run("MATCH (n:Canon) DETACH DELETE n RETURN count(n) AS c").single()
    return rec["c"] if rec else 0


def counts(session) -> tuple[int, int, int]:
    ep = session.run("MATCH (e:Episode) RETURN count(e) AS c").single()["c"]
    fa = session.run("MATCH (f:Fact) RETURN count(f) AS c").single()["c"]
    no = session.run("MATCH (n:Canon) RETURN count(n) AS c").single()["c"]
    return ep, fa, no


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Seed the ANDHERA canon into Neo4j.")
    ap.add_argument("--reset", action="store_true", help="delete this seed batch before seeding")
    ap.add_argument("--wipe", action="store_true", help="delete the ENTIRE canon before seeding")
    ap.add_argument("--reset-only", action="store_true", help="delete the seed batch and exit")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = ap.parse_args(argv)

    if not settings.graph_configured:
        print("ERROR: Neo4j not configured (NEO4J_URI / NEO4J_PASSWORD missing).")
        print("Run from backend/ so backend/.env is loaded.")
        return 2

    # Build everything in memory first (so the assertion fails before any write).
    episodes = build_episodes()
    entities = build_entities()
    relations = build_relations()
    stable = build_stable_facts()
    hero = build_hero_facts()
    events = build_event_facts()
    assert_no_accidental_conflicts(stable, hero)
    facts = stable + hero + events

    total_entities = sum(len(v) for v in entities.values())
    total_rels = sum(len(v) for v in relations.values())
    print(
        f"Prepared: {len(episodes)} episodes · {total_entities} entities · "
        f"{total_rels} relations · {len(facts)} facts "
        f"({len(stable)} bible + {len(hero)} hero + {len(events)} event)."
    )

    if not args.yes:
        action = "WIPE ALL canon then " if args.wipe else ("reset batch then " if args.reset else "")
        resp = input(f"About to {action}seed into Neo4j. Continue? [y/N] ").strip().lower()
        if resp not in {"y", "yes"}:
            print("Aborted.")
            return 1

    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_username, settings.neo4j_password)
    )
    try:
        with driver.session(database=settings.neo4j_database) as session:
            if args.reset_only:
                removed = reset_batch(session)
                print(f"Removed {removed} seed-batch nodes. Done.")
                return 0
            if args.wipe:
                removed = wipe_all(session)
                print(f"Wiped {removed} canon nodes.")
            elif args.reset:
                removed = reset_batch(session)
                print(f"Removed {removed} prior seed-batch nodes.")

            print("Writing indexes…")
            write_indexes(session)
            print("Writing episodes…")
            write_episodes(session, episodes)
            print("Writing entities…")
            write_entities(session, entities)
            print("Writing relations…")
            write_relations(session, relations)
            print("Writing facts (this is the big one)…")
            write_facts(session, facts)

            ep, fa, no = counts(session)
            print(f"\nDone. Canon now holds: {ep} episodes · {fa} facts · {no} total nodes.")
            print(f"Estimated continuity load: ≈{ep * PAGES_PER_EPISODE} pages.")
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
