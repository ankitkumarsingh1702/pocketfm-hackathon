"""Decide the cast once, before a word of prose exists.

Today names are invented inside scene one and carried forward by a rolling
summary. Over six scenes that survives. Over three hundred it does not: the
summary is rewritten each time, and a detail lives only by being re-selected at
every step. Names drift, ages drift, and the character who limped in chapter
three walks fine in chapter thirty.

So the cast is fixed up front by one call, written into the bible, and passed to
every scene unchanged. It is the cheapest fix in the long-form design — one
call for the whole book — and it removes an entire category of failure.

It also does something the per-scene approach cannot: choose names that fit each
other. A cast invented one scene at a time gives you a Leo, a Mr Ollerman, and a
Kaito in the same story. Cast together, they belong to one world.

    python casting.py stories/reveal.txt --genre horror
"""

import argparse
import sys
from pathlib import Path
from typing import List

from pydantic import BaseModel, Field

from bible import Entity, Place, StoryBible
from genre_pack import GenrePack, available_packs, load_pack
from models import StorySkeleton

CASTING_SYSTEM = """You are casting a story before it is written.

You are given the ROLES of a plot — described by function, never by name — and a \
GENRE BRIEF. Give each role a concrete identity that belongs in that genre, and \
name the places the story needs.

Rules:

1. ONE WORLD. The cast must belong together: same culture, same era, same naming \
convention, unless the plot itself requires an outsider. A story with a Leo, a \
Mr Ollerman and a Kaito in it has been cast three separate times.

2. THE FUNCTION IS FIXED. You are naming and dressing the role, not changing it. \
If the role is the one who withholds something, your character withholds it. Do \
not soften a role because you have made them likeable.

3. DESCRIBE WHAT A READER WOULD SEE. Physical presence and manner, in one or two \
sentences. A detail a later scene can use — how they hold themselves, what their \
hands do, how they speak. Not biography, not psychology.

4. RELATIONSHIPS ARE STRUCTURAL. State what each pair is to each other in the \
plot's terms: employer, sibling, rival, debtor. This is what stops chapter thirty \
inventing a friendship chapter three ruled out.

5. PLACES ARE FEW AND SPECIFIC. Name only the places the plot needs. Each gets a \
sentence that a scene can build on.

Everything you invent here is permanent. A later scene may add to it and may not \
contradict it."""


class CastEntity(BaseModel):
    slug: str = Field(description="The role slug exactly as given. Do not invent new slugs.")
    name: str = Field(description="The name used for this character throughout.")
    description: str = Field(
        description=(
            "One or two sentences: physical presence and manner, the kind of "
            "detail a later scene can reuse. No biography."
        )
    )
    relationships: dict = Field(
        default_factory=dict,
        description="{other_role_slug: what they are to each other, in plot terms}",
    )


class CastPlace(BaseModel):
    slug: str = Field(description="Short snake_case handle, e.g. 'institution', 'family_house'.")
    name: str = Field(description="What the story calls it.")
    description: str = Field(description="One sentence a scene can build on.")


class Casting(BaseModel):
    entities: List[CastEntity] = Field(description="Exactly one per role given, same slugs.")
    places: List[CastPlace] = Field(description="Only the places the plot needs. Two to five.")
    register_notes: str = Field(
        description=(
            "One or two sentences fixing era, naming convention, and how people "
            "address each other. Every scene will follow this."
        )
    )


def cast(skeleton: StorySkeleton, pack: GenrePack) -> Casting:
    """One call for the whole story."""
    from llm import structured

    roles = "\n".join(
        f"  {role.slug} — appears in: "
        + ", ".join(b.action for b in skeleton.beats if b.actor_role == role.slug)[:220]
        for role in skeleton.roles
    )
    prompt = (
        f"{pack.as_brief()}\n\n"
        f"LOGLINE (genre-neutral): {skeleton.logline}\n\n"
        f"ROLES TO CAST:\n{roles}\n\n"
        "Cast every role listed, keeping its slug exactly."
    )
    # Some invention, but not so much that the cast stops cohering.
    return structured(CASTING_SYSTEM, prompt, Casting, temperature=0.7)


def to_bible(casting: Casting, genre: str) -> StoryBible:
    """Seed a bible from the casting. This is the canon every scene reads."""
    story_bible = StoryBible(genre=genre)
    for entity in casting.entities:
        story_bible.add_entity(
            Entity(
                slug=entity.slug,
                name=entity.name,
                description=entity.description,
                relationships={k: v for k, v in (entity.relationships or {}).items() if isinstance(v, str)},
            )
        )
    for place in casting.places:
        story_bible.add_place(
            Place(slug=place.slug, name=place.name, description=place.description)
        )
    if casting.register_notes.strip():
        story_bible.add_fact(casting.register_notes.strip(), scene="casting")
    return story_bible


def check_casting(casting: Casting, skeleton: StorySkeleton) -> List[str]:
    """Deterministic checks. A miscast role is cheaper to catch now than in chapter 30."""
    complaints: List[str] = []
    wanted = {r.slug for r in skeleton.roles}
    got = {e.slug for e in casting.entities}

    for slug in sorted(wanted - got):
        complaints.append(f"role {slug!r} was not cast")
    for slug in sorted(got - wanted):
        complaints.append(f"cast an unknown role {slug!r} — slugs must match the skeleton")

    seen: dict = {}
    for entity in casting.entities:
        key = entity.name.strip().lower()
        if key in seen:
            complaints.append(f"{entity.name!r} used for both {seen[key]!r} and {entity.slug!r}")
        seen[key] = entity.slug
        if not entity.description.strip():
            complaints.append(f"role {entity.slug!r} has no description")

    for entity in casting.entities:
        for other in (entity.relationships or {}):
            if other not in wanted:
                complaints.append(
                    f"{entity.slug!r} claims a relationship to unknown role {other!r}"
                )

    if not casting.places:
        complaints.append("no places were named")
    return sorted(set(complaints))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cast a story before writing it.")
    parser.add_argument("story", help="a story .txt")
    parser.add_argument("--genre", required=True, choices=available_packs())
    parser.add_argument("--out", help="write the seeded bible.json here")
    args = parser.parse_args()

    from extract import extract_clean

    print(f"extracting {args.story}", file=sys.stderr)
    skeleton, _ = extract_clean(Path(args.story).read_text())

    print(f"casting for {args.genre}", file=sys.stderr)
    casting = cast(skeleton, load_pack(args.genre))

    complaints = check_casting(casting, skeleton)
    print()
    print(f"REGISTER  {casting.register_notes}")
    print()
    print("CAST")
    for entity in casting.entities:
        print(f"  {entity.slug:<20} {entity.name}")
        print(f"  {'':<20} {entity.description}")
        for other, relation in (entity.relationships or {}).items():
            print(f"  {'':<20}   to {other}: {relation}")
    print()
    print("PLACES")
    for place in casting.places:
        print(f"  {place.slug:<20} {place.name} — {place.description}")

    if complaints:
        print()
        print("CASTING LINT", file=sys.stderr)
        for complaint in complaints:
            print(f"  - {complaint}", file=sys.stderr)
    else:
        print()
        print("casting lint: clean", file=sys.stderr)

    if args.out:
        to_bible(casting, args.genre).save(Path(args.out))
        print(f"wrote {args.out}", file=sys.stderr)
