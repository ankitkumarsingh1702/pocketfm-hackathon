"""Novel-length conversion: the orchestrator.

Wires the pieces the short pipeline does not have — segmentation, a hierarchical
skeleton, a cast fixed up front, a story bible instead of a rolling summary, and
verification done per chapter — into one run.

    story -> chunks -> chapter skeletons -> acts -> book spine
                                                      |
                                              cast + outline
                                                      |
                            chapter by chapter, scene by scene, bible-fed
                                                      |
                                        verify each chapter against its beats

Three things here that the short pipeline gets wrong at length:

  IDS ARE GLOBAL      Each chapter extraction returns b1, b2, b3. Left alone,
                      chapter 12's b2 collides with chapter 3's. Ids are rewritten
                      to c03b02 on the way in, and causal edges remapped with them.

  ROLES ARE UNIFIED   Chapter 3 calls her "protagonist", chapter 9 calls her
                      "the_caregiver". Same woman. Unified by the source name,
                      which extraction preserves verbatim — deterministic, no call.

  STATE IS RETRIEVED  Scenes read a slice of the bible, not a summary of a summary.

    python longform.py book.txt --genre horror --limit 2
    python longform.py book.txt --genre horror --plan-only
"""

import argparse
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from bible import ProposedFact, StoryBible, check_continuity, merge_proposals
from casting import cast, check_casting, to_bible
from delivery import check_delivery, check_links, delivered_ids, preserved_edges, undelivered
from extract import extract_clean
from genre_pack import GenrePack, available_packs, load_pack
from models import Beat, Role, StorySkeleton
from segment import Chunk, segment
from store import SceneRecord, Store, new_run
from transform import MAX_BEATS_PER_SCENE, _render_spine, plan_scenes
from verify import W_ALL_BEATS, W_EDGES, W_LOAD_BEARING

# Chapters per act. Acts exist to give the outline something to plan against;
# they are not a literary claim about three-act structure.
CHAPTERS_PER_ACT = 4

# The tail of the previous scene, verbatim. A summary loses voice at the seam;
# the actual closing sentences do not.
SEAM_WORDS = 180


# ---------------------------------------------------------------------------
# hierarchical skeleton
# ---------------------------------------------------------------------------


class ChapterSkeleton(BaseModel):
    """One chunk's worth of plot, with globally unique beat ids."""

    index: int
    title: Optional[str] = None
    words: int = 0
    skeleton: StorySkeleton

    @property
    def id(self) -> str:
        return f"ch{self.index:03d}"

    @property
    def label(self) -> str:
        return self.title or f"chapter {self.index + 1}"


class ActSummary(BaseModel):
    """What a run of chapters does to the book."""

    summary: str = Field(description="Three or four sentences. What happens across these chapters.")
    function: str = Field(
        description="One sentence: what this act does to the whole story — establishes, escalates, inverts, resolves."
    )


class ChapterPlan(BaseModel):
    """The genre-concrete brief for one chapter."""

    chapter_id: str = Field(description="The chapter id exactly as given, e.g. 'ch003'.")
    setting: str = Field(description="Where and when this chapter happens, in the target genre.")
    intent: str = Field(description="One sentence: what this chapter must do to the reader.")
    opening_note: str = Field(description="How to come into the chapter, given what preceded it.")


class ActOutline(BaseModel):
    chapters: List[ChapterPlan] = Field(description="Exactly one per chapter given, in order.")


class LongScene(BaseModel):
    """A scene, plus what it added to the canon."""

    prose: str = Field(
        description=(
            "The scene as continuous narrative prose in the target genre. No "
            "headings, no beat ids, no meta-commentary."
        )
    )
    beats_covered: List[str] = Field(
        description="Ids of the spine beats this scene delivers. Checked independently."
    )
    proposed_facts: List[ProposedFact] = Field(
        default_factory=list,
        description=(
            "Concrete things this scene made true that a later chapter must not "
            "contradict. Two to five. Physical details and revealed information, "
            "not plot summary."
        ),
    )


class BookSkeleton(BaseModel):
    logline: str = ""
    roles: List[Role] = Field(default_factory=list)
    chapters: List[ChapterSkeleton] = Field(default_factory=list)
    acts: List[ActSummary] = Field(default_factory=list)
    act_chapters: List[List[int]] = Field(default_factory=list)

    def beats(self) -> List[Beat]:
        return [b for c in self.chapters for b in c.skeleton.beats]

    def edges(self) -> List[tuple]:
        return [e for c in self.chapters for e in c.skeleton.causal_edges]


# ---------------------------------------------------------------------------
# stage 1 — extract, bottom-up
# ---------------------------------------------------------------------------


def _renumber(skeleton: StorySkeleton, index: int) -> StorySkeleton:
    """Rewrite b1 -> c003b01 so ids are unique across the whole book."""
    mapping = {b.id: f"c{index:03d}b{n + 1:02d}" for n, b in enumerate(skeleton.beats)}
    beats = [
        Beat(
            id=mapping[b.id],
            actor_role=b.actor_role,
            action=b.action,
            causes=[mapping[c] for c in b.causes if c in mapping],
            outcome=b.outcome,
            load_bearing=b.load_bearing,
        )
        for b in skeleton.beats
    ]
    return StorySkeleton(logline=skeleton.logline, roles=skeleton.roles, beats=beats)


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_") or "role"


def unify_roles(chapters: List[ChapterSkeleton]) -> Dict[str, Role]:
    """One canonical role per person, keyed by the name the source text uses.

    Chapter 3 may call her `protagonist` and chapter 9 `the_caregiver`; both
    carry `name` verbatim from the source, and the source calls her the same
    thing throughout. So this needs no model call — which matters, because a
    reconciliation call that got it wrong would corrupt the cast and the bible
    together.
    """
    by_name: Dict[str, Dict[str, int]] = {}
    for chapter in chapters:
        for role in chapter.skeleton.roles:
            key = role.name.strip().lower()
            if not key:
                continue
            by_name.setdefault(key, {})
            by_name[key][role.slug] = by_name[key].get(role.slug, 0) + 1

    canonical: Dict[str, Role] = {}
    used: set = set()
    for key, slugs in by_name.items():
        best = max(slugs.items(), key=lambda kv: (kv[1], -len(kv[0])))[0]
        slug = best if best not in used else f"{best}_{_slugify(key)[:12]}"
        used.add(slug)
        name = next(
            r.name
            for c in chapters
            for r in c.skeleton.roles
            if r.name.strip().lower() == key
        )
        canonical[key] = Role(slug=slug, name=name)
    return canonical


def _apply_roles(chapter: ChapterSkeleton, canonical: Dict[str, Role]) -> ChapterSkeleton:
    """Point every beat at the canonical slug for the person it names."""
    local = {r.slug: r.name.strip().lower() for r in chapter.skeleton.roles}
    beats = []
    for beat in chapter.skeleton.beats:
        key = local.get(beat.actor_role)
        slug = canonical[key].slug if key and key in canonical else beat.actor_role
        beats.append(beat.model_copy(update={"actor_role": slug}))
    used = {b.actor_role for b in beats}
    roles = [r for r in canonical.values() if r.slug in used]
    return chapter.model_copy(
        update={
            "skeleton": StorySkeleton(
                logline=chapter.skeleton.logline, roles=roles or chapter.skeleton.roles, beats=beats
            )
        }
    )


ACT_SYSTEM = """You summarise a run of chapters from a story.

You are given each chapter's own summary and its load-bearing beats — the events \
that, if deleted, would break the story. Say what happens across them, and what \
this run of chapters does to the story as a whole.

Write flat and functional. No genre language, no proper nouns beyond what you are \
given. This is a structural description, not a blurb."""


def summarise_act(chapters: List[ChapterSkeleton]) -> ActSummary:
    """One call per act, over summaries and load-bearing beats only."""
    from llm import structured

    lines = []
    for chapter in chapters:
        lines.append(f"{chapter.id} — {chapter.label}")
        lines.append(f"  premise: {chapter.skeleton.logline}")
        for beat in chapter.skeleton.beats:
            if beat.load_bearing:
                lines.append(f"    {beat.id}: {beat.actor_role} — {beat.action}")
    return structured(ACT_SYSTEM, "\n".join(lines), ActSummary)


BOOK_SYSTEM = """You state the spine of a whole story from its act summaries.

One sentence naming who wants what and what stands in the way, by function and \
never by name. Flat, functional, no genre language."""


class BookSpine(BaseModel):
    logline: str = Field(description="One sentence. Roles by function, no proper nouns.")


def extract_book(
    text: str,
    store: Optional[Store] = None,
    limit: int = 0,
    target_words: int = 2500,
    verbose: bool = True,
) -> BookSkeleton:
    """Segment, extract every chunk, unify, and reduce upward."""
    from llm import structured

    chunks: List[Chunk] = segment(text, target_words)
    if limit:
        chunks = chunks[:limit]
    if store:
        store.touch(stage="segment", chunks=len(chunks), note=f"{len(chunks)} chunks")
        for chunk in chunks:
            store.put_chunk(chunk.index, chunk.text)

    if verbose:
        total = sum(c.words for c in chunks)
        print(f"  {len(chunks)} chunks, {total} words", file=sys.stderr)

    chapters: List[ChapterSkeleton] = []
    for chunk in chunks:
        started = time.time()
        skeleton, _ = extract_clean(chunk.text)
        chapter = ChapterSkeleton(
            index=chunk.index,
            title=chunk.title,
            words=chunk.words,
            skeleton=_renumber(skeleton, chunk.index),
        )
        chapters.append(chapter)
        if store:
            store.put_json(f"skeletons/chapter-{chunk.index:03d}.json", chapter)
            store.touch(stage="extract", note=f"{chapter.id} extracted")
        if verbose:
            print(
                f"    {chapter.id} {chunk.words:>5}w -> {len(chapter.skeleton.beats):>2} beats, "
                f"{len(chapter.skeleton.load_bearing_ids):>2} load-bearing "
                f"({time.time() - started:.0f}s)",
                file=sys.stderr,
            )

    canonical = unify_roles(chapters)
    chapters = [_apply_roles(c, canonical) for c in chapters]
    if verbose:
        print(
            f"  {len(canonical)} people across the book: "
            + ", ".join(f"{r.slug}={r.name}" for r in list(canonical.values())[:6]),
            file=sys.stderr,
        )

    act_chapters = [
        list(range(i, min(i + CHAPTERS_PER_ACT, len(chapters))))
        for i in range(0, len(chapters), CHAPTERS_PER_ACT)
    ]
    acts: List[ActSummary] = []
    for group in act_chapters:
        acts.append(summarise_act([chapters[i] for i in group]))
        if verbose:
            print(f"    act {len(acts)} over {len(group)} chapters", file=sys.stderr)

    spine = structured(
        BOOK_SYSTEM,
        "\n\n".join(f"ACT {n + 1}: {a.summary}\nFUNCTION: {a.function}" for n, a in enumerate(acts)),
        BookSpine,
    )

    book = BookSkeleton(
        logline=spine.logline,
        roles=list(canonical.values()),
        chapters=chapters,
        acts=acts,
        act_chapters=act_chapters,
    )
    if store:
        store.put_json("skeletons/book.json", book)
    return book


# ---------------------------------------------------------------------------
# stage 2 — outline
# ---------------------------------------------------------------------------


OUTLINE_SYSTEM = """You plan the chapters of a genre rewrite before it is written.

You are given the cast (already fixed — use these names), a genre brief, what this \
act does to the story, and each chapter's beats. For every chapter, say where and \
when it happens in the new genre, what it must do to the reader, and how to come \
into it from what preceded.

The beats are fixed. You are deciding the surface: setting, era, what the obstacles \
physically are. Keep it consistent across the chapters you are planning — one world, \
not one per chapter.

Be concrete. "A sealed records room in the basement, after hours" is usable; \
"somewhere tense" is not."""


def outline_act(
    book: BookSkeleton,
    act_index: int,
    pack: GenrePack,
    story_bible: StoryBible,
) -> ActOutline:
    """One call per act, producing a plan for each of its chapters."""
    from llm import structured

    indices = book.act_chapters[act_index]
    act = book.acts[act_index]

    lines = [
        story_bible.as_brief(),
        "",
        pack.as_brief(),
        "",
        f"THIS ACT: {act.summary}",
        f"ITS FUNCTION: {act.function}",
        "",
        "CHAPTERS TO PLAN:",
    ]
    for i in indices:
        chapter = book.chapters[i]
        lines.append(f"  {chapter.id}")
        for beat in chapter.skeleton.beats:
            mark = "[PIVOTAL] " if beat.load_bearing else ""
            lines.append(f"      {beat.id}: {mark}{beat.actor_role} — {beat.action}")
    return structured(OUTLINE_SYSTEM, "\n".join(lines), ActOutline)


# ---------------------------------------------------------------------------
# stage 3 — write
# ---------------------------------------------------------------------------


SCENE_SYSTEM = """You write one scene of a story in a specified genre.

You are given a PLOT SPINE — the beats this scene must contain — a GENRE BRIEF, \
the STORY BIBLE of what is already established, and the CHAPTER PLAN.

What you MUST preserve:
- every beat in the spine, in the given order
- who does what: if the spine says a role acts, that role acts
- outcomes: a failure stays a failure, a reveal still reveals, a reversal inverts
- causality: if a beat causes another, your scene makes that link legible

DRAMATISE, DO NOT REPORT. Every beat must happen on the page, in this scene, in \
front of the reader. A beat that a character remembers, mentions, or refers to as \
having happened earlier has NOT been delivered. If the spine gives you an event, \
the reader watches it occur.

The STORY BIBLE is fixed. Use those names, those places, those established facts. \
You may add to it; you may not contradict it. Never rename anyone.

Write continuous narrative prose. No headings, no beat labels, no scene numbers. \
Begin in the scene. If the previous scene's closing lines are supplied, continue \
from that voice and moment without restating them.

Roughly 250-400 words per beat you are covering."""

REDO_PREFIX = """Your previous version of this scene did not deliver every beat.

An independent reader checked the passage against the beats and found these \
missing or wrong:

{missing}

Write the scene again. Keep the setting, the names and the voice. Put each of \
those events on the page as something the reader watches happen — not recalled, \
not mentioned, not implied — with the right character doing it and the stated \
outcome."""


def write_scene(
    beats: List[Beat],
    chapter: ChapterSkeleton,
    plan: Optional[ChapterPlan],
    pack: GenrePack,
    story_bible: StoryBible,
    seam: str,
    is_first: bool,
    is_last: bool,
    missing: Optional[List[Beat]] = None,
    missing_notes: Optional[Dict[str, str]] = None,
) -> LongScene:
    """One scene call, fed a slice of the bible rather than a rolling summary."""
    from llm import structured

    actors = {b.actor_role for b in beats}
    view = story_bible.slice(actors)

    parts = [
        pack.as_brief(),
        "",
        view.as_brief(),
        "",
    ]
    if plan:
        parts += [
            f"CHAPTER PLAN — setting: {plan.setting}",
            f"                intent: {plan.intent}",
            f"               opening: {plan.opening_note}",
            "",
        ]
    parts.append(_render_spine(beats, chapter.skeleton))
    if seam:
        parts += ["", "THE PREVIOUS SCENE ENDED (continue from this voice and moment):", seam]
    elif is_first:
        parts += ["", "This is the opening of the story. Establish the world from nothing."]
    if is_last:
        parts += ["", "This is the FINAL scene of the story. Land it; do not set up more."]

    prompt = "\n".join(parts)
    if missing:
        notes = missing_notes or {}
        complaint = "\n".join(
            f"  - {b.id}: {b.action}" + (f"  [{notes[b.id]}]" if b.id in notes else "")
            for b in missing
        )
        prompt = REDO_PREFIX.format(missing=complaint) + "\n\n" + prompt

    from transform import TRANSFORM_TEMPERATURE

    return structured(SCENE_SYSTEM, prompt, LongScene, temperature=TRANSFORM_TEMPERATURE)


def write_chapter(
    book: BookSkeleton,
    chapter: ChapterSkeleton,
    plan: Optional[ChapterPlan],
    pack: GenrePack,
    story_bible: StoryBible,
    store: Optional[Store],
    seam: str = "",
    is_first: bool = False,
    is_last: bool = False,
    verbose: bool = True,
) -> str:
    """Write one chapter, scene by scene, checking delivery as it goes."""
    scenes = plan_scenes(chapter.skeleton, MAX_BEATS_PER_SCENE)
    prose_parts: List[str] = []

    for n, beats in enumerate(scenes):
        scene_id = f"{chapter.id}-s{n:02d}"
        last_scene = is_last and n == len(scenes) - 1
        scene = write_scene(
            beats, chapter, plan, pack, story_bible, seam, is_first and n == 0, last_scene
        )

        # Never trust beats_covered. Ask a reader that was not told what we hoped.
        report = check_delivery(scene.prose, beats)
        short = undelivered(report, beats, load_bearing_only=True)
        attempts = 1
        if short:
            notes = {v.beat_id: v.note for v in report.verdicts if not v.delivered}
            scene = write_scene(
                beats, chapter, plan, pack, story_bible, seam,
                is_first and n == 0, last_scene, missing=short, missing_notes=notes,
            )
            report = check_delivery(scene.prose, beats)
            short = undelivered(report, beats, load_bearing_only=True)
            attempts = 2

        verified = delivered_ids(report, beats)
        added = merge_proposals(
            story_bible, scene.proposed_facts, scene=scene_id, chapter=chapter.id,
            beats=[b.id for b in beats],
        )

        if store:
            store.put_scene(
                SceneRecord(
                    scene_id=scene_id,
                    chapter=chapter.id,
                    beats_assigned=[b.id for b in beats],
                    beats_claimed=scene.beats_covered,
                    beats_verified=verified,
                    attempts=attempts,
                    words=len(scene.prose.split()),
                    prose=scene.prose,
                    bible_slice=story_bible.slice({b.actor_role for b in beats}).as_brief(),
                    facts_added=added,
                )
            )
        if verbose:
            over = sorted(set(scene.beats_covered) - set(verified))
            flag = f"  OVERCLAIMED {','.join(over)}" if over else ""
            retry = " (retried)" if attempts > 1 else ""
            print(
                f"      {scene_id} {len(scene.prose.split()):>4}w  "
                f"{len(verified)}/{len(beats)} delivered{retry}{flag}",
                file=sys.stderr,
            )

        prose_parts.append(scene.prose.strip())
        seam = " ".join(scene.prose.split()[-SEAM_WORDS:])

    return "\n\n".join(prose_parts)


# ---------------------------------------------------------------------------
# stage 4 — verify, per chapter
# ---------------------------------------------------------------------------


def verify_chapter(chapter: ChapterSkeleton, prose: str) -> Dict[str, object]:
    """Score one chapter's prose against its own beats. Bounded, and parallelisable."""
    beats = chapter.skeleton.beats
    edges = chapter.skeleton.causal_edges
    delivery = check_delivery(prose, beats)
    links = check_links(prose, edges, beats) if edges else None

    kept = set(delivered_ids(delivery, beats))
    edges_kept = preserved_edges(links, edges) if links else []
    lb = chapter.skeleton.load_bearing_ids

    components = [
        ("load_bearing_recall", W_LOAD_BEARING, len([i for i in lb if i in kept]), len(lb)),
        ("beat_recall", W_ALL_BEATS, len(kept), len(beats)),
        ("edge_recall", W_EDGES, len(edges_kept), len(edges)),
    ]
    live = sum(w for _, w, _, d in components if d > 0)
    detail: Dict[str, object] = {"chapter": chapter.id}
    total = 0.0
    for name, weight, count, denom in components:
        detail[name] = round(count / denom, 4) if denom else None
        detail[f"{name}_counts"] = f"{count}/{denom}"
        if denom and live:
            total += (weight / live) * (count / denom)
    detail["fidelity"] = round(total, 4)
    detail["missing_load_bearing"] = [i for i in lb if i not in kept]
    detail["broken_edges"] = [f"{s}->{t}" for (s, t) in edges if (s, t) not in set(edges_kept)]
    detail["beat_notes"] = {v.beat_id: v.note for v in delivery.verdicts if not v.delivered}
    detail["load_bearing_total"] = len(lb)
    return detail


def aggregate(chapter_reports: List[Dict[str, object]]) -> Dict[str, object]:
    """Book fidelity, weighted by how much plot each chapter carries.

    A chapter with six load-bearing beats counts for more than one with a single
    supporting beat — an unweighted mean would let a thin chapter mask a broken
    pivotal one.
    """
    if not chapter_reports:
        return {"fidelity": 0.0, "chapters": 0}
    weights = [max(1, int(r.get("load_bearing_total") or 1)) for r in chapter_reports]
    total = sum(w * float(r["fidelity"]) for w, r in zip(weights, chapter_reports)) / sum(weights)
    worst = min(chapter_reports, key=lambda r: r["fidelity"])
    return {
        "fidelity": round(total, 4),
        "chapters": len(chapter_reports),
        "weakest_chapter": worst["chapter"],
        "weakest_fidelity": worst["fidelity"],
        "chapters_below_60": [r["chapter"] for r in chapter_reports if r["fidelity"] < 0.60],
        "per_chapter": chapter_reports,
    }


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------


def run(
    text: str,
    genre: str,
    run_id: Optional[str] = None,
    limit: int = 0,
    target_words: int = 2500,
    plan_only: bool = False,
    verbose: bool = True,
) -> Dict[str, object]:
    """The whole thing. Every artifact lands in the run directory as it is made."""
    pack = load_pack(genre)
    run_id = run_id or f"{genre}-{int(time.time())}"
    store = new_run(run_id, genre, text)
    started = time.time()

    try:
        if verbose:
            print(f"[1/4] extracting  ({len(text.split())} words)", file=sys.stderr)
        book = extract_book(text, store, limit=limit, target_words=target_words, verbose=verbose)

        if verbose:
            print(f"[2/4] casting for {genre}", file=sys.stderr)
        store.touch(stage="cast")
        spine = StorySkeleton(logline=book.logline, roles=book.roles, beats=book.beats())
        casting = cast(spine, pack)
        complaints = check_casting(casting, spine)
        story_bible = to_bible(casting, genre)
        store.put_json("casting.json", casting)
        if verbose:
            print(
                "      " + ", ".join(f"{e.slug}={e.name}" for e in casting.entities[:6]),
                file=sys.stderr,
            )
            if complaints:
                for complaint in complaints:
                    print(f"      casting lint: {complaint}", file=sys.stderr)

        if verbose:
            print(f"[3/4] outlining {len(book.acts)} act(s)", file=sys.stderr)
        store.touch(stage="outline")
        plans: Dict[str, ChapterPlan] = {}
        for act_index in range(len(book.acts)):
            outline = outline_act(book, act_index, pack, story_bible)
            for plan in outline.chapters:
                plans[plan.chapter_id] = plan
        store.put_json("outline.json", {"chapters": [p.model_dump() for p in plans.values()]})
        if verbose:
            for chapter in book.chapters:
                plan = plans.get(chapter.id)
                print(f"      {chapter.id}: {plan.setting[:72] if plan else '(no plan)'}", file=sys.stderr)

        if plan_only:
            story_bible.save(store.root / "bible.json")
            store.touch(status="done", stage="plan-only")
            return {"run_id": run_id, "book": book, "plans": plans, "planned_only": True}

        if verbose:
            print(f"[4/4] writing {len(book.chapters)} chapter(s)", file=sys.stderr)
        store.touch(stage="write")
        chapter_prose: Dict[str, str] = {}
        seam = ""
        for n, chapter in enumerate(book.chapters):
            if verbose:
                print(f"    {chapter.id} ({len(chapter.skeleton.beats)} beats)", file=sys.stderr)
            prose = write_chapter(
                book, chapter, plans.get(chapter.id), pack, story_bible, store,
                seam=seam, is_first=(n == 0), is_last=(n == len(book.chapters) - 1),
                verbose=verbose,
            )
            chapter_prose[chapter.id] = prose
            store.put_text(f"chapters/{chapter.id}.txt", prose)
            story_bible.save(store.root / "bible.json")
            seam = " ".join(prose.split()[-SEAM_WORDS:])

        if verbose:
            print("verifying, chapter by chapter", file=sys.stderr)
        store.touch(stage="verify")
        reports = []
        for chapter in book.chapters:
            report = verify_chapter(chapter, chapter_prose[chapter.id])
            reports.append(report)
            if verbose:
                print(
                    f"    {chapter.id}  fidelity {report['fidelity']:.1%}  "
                    f"lb {report['load_bearing_recall_counts']}  "
                    f"beats {report['beat_recall_counts']}  edges {report['edge_recall_counts']}",
                    file=sys.stderr,
                )

        result = aggregate(reports)
        result["continuity"] = check_continuity(story_bible)
        result["overclaims"] = store.overclaims()
        result["run_id"] = run_id
        result["genre"] = genre
        result["words"] = sum(len(p.split()) for p in chapter_prose.values())
        result["seconds"] = round(time.time() - started, 1)

        store.put_json("report.json", result)
        store.put_text("rewritten.txt", "\n\n".join(chapter_prose[c.id] for c in book.chapters))
        story_bible.save(store.root / "bible.json")
        store.touch(status="done", stage="")
        return result

    except Exception as exc:
        store.touch(status="error", error=str(exc))
        raise


def print_report(result: Dict[str, object]) -> None:
    print("=" * 70)
    print(f"BOOK FIDELITY  {result['fidelity']:.2%}   over {result['chapters']} chapters")
    print("=" * 70)
    for report in result.get("per_chapter", []):
        print(
            f"  {report['chapter']}  {report['fidelity']:>7.1%}  "
            f"lb {report['load_bearing_recall_counts']:<7} "
            f"beats {report['beat_recall_counts']:<7} edges {report['edge_recall_counts']}"
        )
        for beat_id, note in (report.get("beat_notes") or {}).items():
            print(f"        {beat_id}: {note[:80]}")
    if result.get("chapters_below_60"):
        print(f"\n  chapters below 60%: {', '.join(result['chapters_below_60'])}")
    if result.get("continuity"):
        print("\n  continuity:")
        for complaint in result["continuity"]:
            print(f"    - {complaint}")
    if result.get("overclaims"):
        print("\n  scenes that claimed beats the check could not find:")
        for scene, beats in result["overclaims"].items():
            print(f"    {scene}: {', '.join(beats)}")
    print(f"\n  {result['words']} words in {result['seconds']}s — artifacts in .cache/runs/{result['run_id']}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert a long story into another genre.")
    parser.add_argument("path", help="a .txt file")
    parser.add_argument("--genre", required=True, choices=available_packs())
    parser.add_argument("--limit", type=int, default=0, help="only the first N chunks")
    parser.add_argument("--target", type=int, default=2500, help="words per chunk")
    parser.add_argument("--plan-only", action="store_true", help="stop after the outline")
    parser.add_argument("--run-id", help="name the run directory")
    args = parser.parse_args()

    outcome = run(
        Path(args.path).read_text(),
        args.genre,
        run_id=args.run_id,
        limit=args.limit,
        target_words=args.target,
        plan_only=args.plan_only,
    )
    if outcome.get("planned_only"):
        print(f"planned only — artifacts in .cache/runs/{outcome['run_id']}/")
    else:
        print_report(outcome)
