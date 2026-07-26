"""The story bible — what replaces the rolling summary.

The short pipeline carries continuity by having each scene write two or three
sentences for the next. Over six scenes that holds. Over three hundred it does
not: scene 200 is reading a summary of a summary of a summary, two hundred
rounds deep, and everything from the first third is gone. Lossy compression
applied recursively converges on noise, and no context window fixes information
the pipeline itself discarded.

A bible is the opposite shape. Facts are written once and stay. Nothing has to
survive re-selection, because nothing is re-written. Scene 300 reads the same
words scene 2 wrote.

Two properties make it work at length:

  APPEND-ONLY   A fact is added, never edited. When something stops being true
                it is revoked, which keeps the history rather than erasing it.
  SLICED        A scene is given only the rows its beats touch. Ten rows, not
                four hundred, so prompt size is flat whether it is chapter 2 or
                chapter 40.

    python bible.py --selftest
"""

import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from pydantic import BaseModel, Field


class Fact(BaseModel):
    """Something that became true, and stayed true until it didn't."""

    id: int
    text: str = Field(description="One sentence, concrete. 'The brass key opens the top drawer.'")
    entities: List[str] = Field(default_factory=list, description="Entity slugs this fact concerns.")
    places: List[str] = Field(default_factory=list)
    chapter: Optional[str] = None
    scene: Optional[str] = None
    beats: List[str] = Field(default_factory=list, description="Beat ids that established it.")
    revoked_by: Optional[int] = Field(
        None, description="Id of the fact that superseded this one, if any."
    )

    @property
    def live(self) -> bool:
        return self.revoked_by is None


class Entity(BaseModel):
    """A character, fixed at casting and not re-invented per scene."""

    slug: str = Field(description="The role slug from the skeleton, or a new one for invented cast.")
    name: str = Field(description="The name used throughout the rewrite.")
    description: str = Field(description="Physical presence and manner. Two sentences at most.")
    relationships: Dict[str, str] = Field(
        default_factory=dict, description="{other_slug: what they are to each other}"
    )


class Place(BaseModel):
    slug: str
    name: str
    description: str


class Revision(BaseModel):
    """Who wrote what, so drift can be traced to the scene that caused it."""

    scene: str
    added_facts: List[int] = Field(default_factory=list)
    revoked_facts: List[int] = Field(default_factory=list)
    note: str = ""


class StoryBible(BaseModel):
    """The canon. Grows; does not degrade."""

    genre: str = ""
    entities: Dict[str, Entity] = Field(default_factory=dict)
    places: Dict[str, Place] = Field(default_factory=dict)
    facts: List[Fact] = Field(default_factory=list)
    revisions: List[Revision] = Field(default_factory=list)

    # -- writing -----------------------------------------------------------

    def add_entity(self, entity: Entity) -> None:
        self.entities[entity.slug] = entity

    def add_place(self, place: Place) -> None:
        self.places[place.slug] = place

    def add_fact(
        self,
        text: str,
        entities: Optional[List[str]] = None,
        places: Optional[List[str]] = None,
        chapter: Optional[str] = None,
        scene: Optional[str] = None,
        beats: Optional[List[str]] = None,
        revokes: Optional[int] = None,
    ) -> Fact:
        """Append a fact. `revokes` marks an earlier one superseded, never deleted."""
        fact = Fact(
            id=len(self.facts) + 1,
            text=text.strip(),
            entities=entities or [],
            places=places or [],
            chapter=chapter,
            scene=scene,
            beats=beats or [],
        )
        self.facts.append(fact)
        if revokes is not None:
            for earlier in self.facts:
                if earlier.id == revokes:
                    earlier.revoked_by = fact.id
        return fact

    def record(self, scene: str, added: List[int], revoked: Optional[List[int]] = None, note: str = "") -> None:
        self.revisions.append(
            Revision(scene=scene, added_facts=added, revoked_facts=revoked or [], note=note)
        )

    # -- reading -----------------------------------------------------------

    def live_facts(self) -> List[Fact]:
        return [f for f in self.facts if f.live]

    def slice(
        self,
        entity_slugs: Iterable[str],
        place_slugs: Iterable[str] = (),
        limit: int = 30,
    ) -> "StoryBible":
        """The rows a scene needs, and nothing else.

        This is the whole reason the design scales. A scene about two characters
        gets those two characters and the facts touching them — the same handful
        of rows in chapter 40 as in chapter 2.

        Facts are returned most-recent-first when truncated, because a scene is
        more likely to contradict something established recently than something
        established in the first chapter.
        """
        wanted: Set[str] = {s for s in entity_slugs if s}
        places: Set[str] = {s for s in place_slugs if s}

        # Pull in anyone directly related to a requested entity: a scene about a
        # protagonist needs to know who her sister is, even if the sister is not
        # in this scene.
        for slug in list(wanted):
            entity = self.entities.get(slug)
            if entity:
                wanted.update(entity.relationships.keys())

        # A fact tied to nobody is a fact about the world — the weather of the
        # story, true wherever a scene is set — so it is always served. Facts
        # tied to a person are served only to scenes that person is in.
        relevant = [
            f
            for f in self.live_facts()
            if not f.entities
            or wanted.intersection(f.entities)
            or places.intersection(f.places)
        ]
        if len(relevant) > limit:
            relevant = relevant[-limit:]

        for fact in relevant:
            places.update(fact.places)

        return StoryBible(
            genre=self.genre,
            entities={s: e for s, e in self.entities.items() if s in wanted},
            places={s: p for s, p in self.places.items() if s in places},
            facts=relevant,
        )

    def as_brief(self) -> str:
        """Render for a prompt. Plain and scannable; the model reads it as reference."""
        if not self.entities and not self.places and not self.facts:
            return "STORY BIBLE: empty — this is the opening scene."

        lines: List[str] = ["STORY BIBLE — established and not revisable:"]
        if self.entities:
            lines.append("")
            lines.append("PEOPLE")
            for entity in self.entities.values():
                lines.append(f"  {entity.name} ({entity.slug}) — {entity.description}")
                for other, relation in entity.relationships.items():
                    other_name = self.entities[other].name if other in self.entities else other
                    lines.append(f"      to {other_name}: {relation}")
        if self.places:
            lines.append("")
            lines.append("PLACES")
            for place in self.places.values():
                lines.append(f"  {place.name} ({place.slug}) — {place.description}")
        live = [f for f in self.facts if f.live]
        if live:
            lines.append("")
            lines.append("FACTS")
            for fact in live:
                lines.append(f"  #{fact.id} {fact.text}")
        # Spell the identifiers out. Shown only 'Alistair Finch (protagonist)',
        # a scene will file its facts under the name and they will never be
        # retrieved again.
        if self.entities or self.places:
            lines.append("")
            lines.append(
                "WHEN TAGGING FACTS, USE THESE EXACT IDENTIFIERS — never names:"
            )
            if self.entities:
                lines.append(f"  people: {', '.join(sorted(self.entities))}")
            if self.places:
                lines.append(f"  places: {', '.join(sorted(self.places))}")
        return "\n".join(lines)

    # -- persistence -------------------------------------------------------

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2))

    @classmethod
    def load(cls, path: Path) -> "StoryBible":
        return cls.model_validate_json(Path(path).read_text())


class ProposedFact(BaseModel):
    """What a scene claims it established. Merged after the scene is accepted."""

    text: str = Field(
        description=(
            "One concrete sentence a later scene must not contradict. Physical "
            "details, revealed information, changed relationships. Not plot "
            "summary — 'the key is brass and opens the top drawer', not 'he "
            "found the key and felt uneasy'."
        )
    )
    entities: List[str] = Field(
        default_factory=list,
        description=(
            "Which people this fact concerns, using the exact identifiers listed "
            "in the story bible — 'protagonist', not 'Alistair Finch'. Leave empty "
            "for facts about the world rather than a person."
        ),
    )
    places: List[str] = Field(
        default_factory=list,
        description="Which places, using the exact identifiers from the story bible.",
    )
    revokes: Optional[int] = Field(
        None, description="Id of an existing fact this supersedes, if it makes one untrue."
    )


def _norm(token: str) -> str:
    """Lowercase, strip punctuation and honorifics, collapse separators."""
    token = re.sub(r"^(mr|mrs|ms|dr|miss|master|the)[\.\s_-]+", "", token.strip().lower())
    return re.sub(r"[^a-z0-9]+", "", token)


def resolve_slug(known: Dict[str, object], token: str) -> Optional[str]:
    """Map whatever a scene called something back to its canonical slug.

    A scene is shown 'Mr. Alistair Finch (protagonist)' and asked for slugs, and
    it will variously answer 'protagonist', 'Mr. Alistair Finch',
    'mr-alistair-finch', or 'alistair_finch'. All four mean the same person.

    Expecting exact identifiers from a model three hundred scenes running is not
    a plan, and the cost of getting it wrong is silent: a fact tagged with a name
    instead of a slug is never served to anyone again.
    """
    if not token:
        return None
    if token in known:
        return token
    target = _norm(token)
    if not target:
        return None
    for slug, entry in known.items():
        if _norm(slug) == target:
            return slug
        name = getattr(entry, "name", "")
        if name and (_norm(name) == target or target in _norm(name) or _norm(name) in target):
            return slug
    return None


def _resolve_all(known: Dict[str, object], tokens: List[str]) -> List[str]:
    resolved = [resolve_slug(known, t) for t in tokens or []]
    return sorted({s for s in resolved if s})


def merge_proposals(
    story_bible: StoryBible,
    proposals: List[ProposedFact],
    scene: str,
    chapter: Optional[str] = None,
    beats: Optional[List[str]] = None,
) -> List[int]:
    """Fold a scene's proposed facts into the bible. Returns the new fact ids.

    Entity and place references are resolved back to canonical slugs on the way
    in, so a fact tagged 'Mr. Alistair Finch' is filed under `protagonist` and
    will actually be retrieved later.
    """
    added: List[int] = []
    revoked: List[int] = []
    for proposal in proposals:
        if not proposal.text.strip():
            continue
        fact = story_bible.add_fact(
            proposal.text,
            entities=_resolve_all(story_bible.entities, proposal.entities),
            places=_resolve_all(story_bible.places, proposal.places),
            chapter=chapter,
            scene=scene,
            beats=beats,
            revokes=proposal.revokes,
        )
        added.append(fact.id)
        if proposal.revokes is not None:
            revoked.append(proposal.revokes)
    story_bible.record(scene, added, revoked)
    return added


# --------------------------------------------------------------------------
# continuity checks — deterministic, zero tokens
# --------------------------------------------------------------------------


def check_continuity(story_bible: StoryBible) -> List[str]:
    """Failures a fidelity score cannot see, but a reader will."""
    complaints: List[str] = []

    # One name per person, one person per name.
    by_name: Dict[str, List[str]] = {}
    for entity in story_bible.entities.values():
        by_name.setdefault(entity.name.lower(), []).append(entity.slug)
    for name, slugs in by_name.items():
        if len(slugs) > 1:
            complaints.append(f"the name {name!r} is used by two roles: {', '.join(sorted(slugs))}")

    # Facts must point at people and places that exist.
    for fact in story_bible.facts:
        for slug in fact.entities:
            if slug not in story_bible.entities:
                complaints.append(f"fact #{fact.id} refers to unknown entity {slug!r}")
        for slug in fact.places:
            if slug not in story_bible.places:
                complaints.append(f"fact #{fact.id} refers to unknown place {slug!r}")

    # A revocation that points nowhere means a scene thought it was overturning
    # something and did not.
    ids = {f.id for f in story_bible.facts}
    for fact in story_bible.facts:
        if fact.revoked_by is not None and fact.revoked_by not in ids:
            complaints.append(f"fact #{fact.id} revoked by unknown fact #{fact.revoked_by}")

    # Someone established with weight and never used again.
    mentioned: Set[str] = set()
    for fact in story_bible.facts:
        mentioned.update(fact.entities)
    for slug in story_bible.entities:
        if slug not in mentioned:
            complaints.append(f"entity {slug!r} was cast but never appears in any fact")

    return sorted(set(complaints))


# --------------------------------------------------------------------------
# self-test
# --------------------------------------------------------------------------


def _selftest() -> int:
    sb = StoryBible(genre="horror")
    sb.add_entity(Entity(slug="protagonist", name="Leo Farrow", description="Junior archivist, 29.",
                         relationships={"gatekeeper": "works under him"}))
    sb.add_entity(Entity(slug="gatekeeper", name="Mr Ollerman", description="Head Curator. Grey suit."))
    sb.add_entity(Entity(slug="sister", name="Nell", description="Lives abroad."))
    sb.add_place(Place(slug="institution", name="The Palliative Wing", description="Leaded windows."))

    print("append-only")
    f1 = sb.add_fact("Something drags across the floor above.", places=["institution"], scene="s1")
    f2 = sb.add_fact("The records were forged by Ollerman.", entities=["gatekeeper"], scene="s2")
    f3 = sb.add_fact("A brass key sits on the desk.", entities=["protagonist"], scene="s6")
    assert [f.id for f in sb.facts] == [1, 2, 3]
    print(f"  three facts, ids {[f.id for f in sb.facts]}")

    print("revocation keeps history")
    f4 = sb.add_fact("Ollerman has resigned.", entities=["gatekeeper"], scene="s9", revokes=f2.id)
    assert sb.facts[1].revoked_by == f4.id, "revocation not recorded"
    assert len(sb.facts) == 4, "revoking must not delete"
    assert [f.id for f in sb.live_facts()] == [1, 3, 4]
    print(f"  fact #2 revoked by #4; all four retained, live = {[f.id for f in sb.live_facts()]}")

    print("slicing")
    view = sb.slice(["protagonist"])
    assert "protagonist" in view.entities
    assert "gatekeeper" in view.entities, "a related entity must come along"
    assert "sister" not in view.entities, "an unrelated entity must not"
    ids = [f.id for f in view.facts]
    assert 3 in ids, "a fact about the protagonist must be included"
    assert 1 in ids, "a world fact with no entity applies everywhere"
    assert 2 not in ids, "a revoked fact must not be served"
    print(f"  slice(protagonist) -> entities {sorted(view.entities)}, facts {ids}")

    print("slice size is bounded")
    big = StoryBible()
    big.add_entity(Entity(slug="p", name="P", description="."))
    for i in range(200):
        big.add_fact(f"fact {i}", entities=["p"])
    assert len(big.slice(["p"], limit=30).facts) == 30
    print("  200 facts, slice capped at 30 — prompt stays flat at any length")

    print("proposals merge with provenance")
    proposals = [
        ProposedFact(text="The drawer is locked.", entities=["protagonist"]),
        ProposedFact(text="Ollerman is dead.", entities=["gatekeeper"], revokes=f4.id),
        ProposedFact(text="   "),  # ignored
    ]
    added = merge_proposals(sb, proposals, scene="s12", chapter="ch4", beats=["b7"])
    assert len(added) == 2, added
    assert sb.revisions[-1].scene == "s12"
    assert sb.revisions[-1].revoked_facts == [f4.id]
    assert sb.facts[-1].chapter == "ch4" and sb.facts[-1].beats == ["b7"]
    print(f"  scene s12 added {added}, revoked {sb.revisions[-1].revoked_facts}")

    print("references are resolved back to slugs")
    # Verbatim from the first long-form run, where every one of 51 facts was
    # filed under a name or an invented slug and none were ever retrievable.
    real = StoryBible()
    real.add_entity(Entity(slug="protagonist", name="Mr. Alistair Finch", description="."))
    real.add_entity(Entity(slug="rival", name="Ms. Elara Vance", description="."))
    real.add_place(Place(slug="institution", name="The Seventh Chamber", description="."))
    merge_proposals(
        real,
        [
            ProposedFact(text="a", entities=["Mr. Alistair Finch"], places=["Seventh Chamber"]),
            ProposedFact(text="b", entities=["mr-alistair-finch", "ms-elara-vance"]),
            ProposedFact(text="c", entities=["elara-vance"]),
            ProposedFact(text="d", entities=["protagonist"]),
            ProposedFact(text="e", entities=["The Butler Who Does Not Exist"]),
        ],
        scene="s1",
    )
    tagged = [f.entities for f in real.facts]
    assert tagged[0] == ["protagonist"], tagged[0]
    assert tagged[1] == ["protagonist", "rival"], tagged[1]
    assert tagged[2] == ["rival"], tagged[2]
    assert tagged[3] == ["protagonist"], tagged[3]
    assert tagged[4] == [], "an unresolvable reference must be dropped, not stored"
    assert real.facts[0].places == ["institution"], real.facts[0].places
    print(f"  names, honorifics and hyphenated slugs all resolved: {tagged}")
    served = [f.text for f in real.slice(["protagonist"]).facts]
    assert set(served) >= {"a", "b", "d"}, served
    assert check_continuity(real) == [], check_continuity(real)
    print(f"  slice(protagonist) now serves {served} — previously it served nothing")

    print("round-trips through disk")
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "bible.json"
        sb.save(path)
        again = StoryBible.load(path)
        assert again.model_dump() == sb.model_dump()
    print("  saved and reloaded identically")

    print("continuity checks")
    bad = StoryBible()
    bad.add_entity(Entity(slug="a", name="Jan", description="."))
    bad.add_entity(Entity(slug="b", name="jan", description="."))
    bad.add_fact("something", entities=["a", "ghost"])
    complaints = check_continuity(bad)
    assert any("two roles" in c for c in complaints), complaints
    assert any("unknown entity" in c for c in complaints), complaints
    assert any("never appears" in c for c in complaints), complaints
    for c in complaints:
        print(f"  caught: {c}")

    assert check_continuity(sb) == [] or all("never appears" in c for c in check_continuity(sb))

    print()
    print("brief rendering")
    print()
    for line in sb.slice(["protagonist"]).as_brief().splitlines():
        print("   " + line)

    print()
    print("bible OK")
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="The story bible.")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--show", help="print a saved bible.json as a prompt brief")
    args = parser.parse_args()

    if args.show:
        print(StoryBible.load(Path(args.show)).as_brief())
        raise SystemExit(0)
    raise SystemExit(_selftest())
