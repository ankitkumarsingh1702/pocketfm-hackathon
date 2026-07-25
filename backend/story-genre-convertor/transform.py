"""Stage 2: skeleton + genre pack -> a rewritten story.

Never one call. A single "rewrite this in horror" request is exactly the failure
mode the verifier exists to catch: the model optimises for the prose in front of
it and quietly loses a beat from the middle. So the skeleton is spent scene by
scene, each call given the handful of beats it is responsible for and nothing
else to lose them among.

Each call returns prose plus its own continuity note, which becomes the next
call's context. The source story is never shown to the transform — only the
skeleton — so there is no surface detail available to copy.

    python transform.py --selftest              # scene planning, no credentials
    python transform.py stories/reveal.txt --genre horror
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Callable, List, Optional

from pydantic import BaseModel, Field

from genre_pack import GenrePack, available_packs, load_pack
from models import Beat, StorySkeleton

# Creative work, unlike extraction and alignment. Deliberately separate from
# SKELETON_TEMPERATURE, which is pinned to 0 so the ceiling check measures the
# extractor rather than the sampler.
TRANSFORM_TEMPERATURE = float(os.environ.get("TRANSFORM_TEMPERATURE", "0.9"))

# Three beats is about a scene's worth. More and the model starts summarising
# the tail of the list to get to the end of the response.
MAX_BEATS_PER_SCENE = 3

TRANSFORM_SYSTEM = """You write one scene of a story in a specified genre.

You are given a PLOT SPINE — a genre-neutral list of the beats this scene must \
contain — and a GENRE BRIEF. The spine is fixed. The genre is yours.

What you MUST preserve:
- every beat in the spine, in the given order
- who does what: if the spine says a role acts, that role acts
- outcomes: a failure stays a failure, a reveal still reveals, a reversal still inverts
- causality: if a beat is listed as causing another, your scene must make that link legible

What you MUST invent, because the spine deliberately omits it:
- setting, era, names, objects, weather, the physical nature of every obstacle
- the literal form of the threat, the prize, the barrier
- imagery, rhythm, dialogue, interiority, register

The genre owns the surface completely. A withheld document can become a sealed \
room, a family secret, a curse, a signed confession, an unsent message — whatever \
the genre wants — as long as the same role withholds the same leverage from the \
same person and the plot turns on it the same way.

Write continuous narrative prose. No headings, no beat labels, no scene numbers, \
no summary of what you are about to do. Begin in the scene. If a rolling summary \
of earlier scenes is supplied, continue seamlessly from it — same names, same \
setting, same tense, same voice. Do not restate it.

Roughly 200-350 words per beat you are covering."""

RETRY_PREFIX = """Your previous version of this scene did not deliver every beat \
it was responsible for.

MISSING:
{missing}

Write the scene again. Keep what worked — same setting, same names, same voice. \
Add the missing beat(s) where they belong in the causal order, and make each one \
actually happen on the page rather than being alluded to."""


class Scene(BaseModel):
    """One scene of the rewritten story."""

    prose: str = Field(
        description=(
            "The scene as continuous narrative prose, in the target genre. No "
            "headings, no beat ids, no meta-commentary. This is the story itself."
        )
    )
    beats_covered: List[str] = Field(
        description=(
            "The ids of the spine beats this scene actually delivers on the page. "
            "Be honest: list an id only if a reader would see that event happen. "
            "A beat you alluded to but did not dramatise is not covered."
        )
    )
    summary_for_next: str = Field(
        description=(
            "Two or three sentences of continuity for whoever writes the next "
            "scene: names introduced, where we are, what has just changed, and "
            "the emotional position we are leaving the protagonist in."
        )
    )


def plan_scenes(skeleton: StorySkeleton, max_beats: int = MAX_BEATS_PER_SCENE) -> List[List[Beat]]:
    """Group consecutive beats into scenes. Deterministic, zero tokens.

    Cuts after every load-bearing beat, so no scene has to carry two pivots — a
    scene with two turns in it will short-change one of them, and the one it
    short-changes is the one the verifier will report as missing.
    """
    scenes: List[List[Beat]] = []
    current: List[Beat] = []
    for beat in skeleton.beats:
        current.append(beat)
        if beat.load_bearing or len(current) >= max_beats:
            scenes.append(current)
            current = []
    if current:
        # A short trailing run of supporting beats belongs with the scene before
        # it rather than as a limp scene of its own.
        if scenes and len(scenes[-1]) + len(current) <= max_beats + 1:
            scenes[-1].extend(current)
        else:
            scenes.append(current)
    return scenes


def _render_spine(beats: List[Beat], skeleton: StorySkeleton) -> str:
    """The beats this scene owns, with the roles they involve."""
    slugs = {b.actor_role for b in beats}
    roles = [r for r in skeleton.roles if r.slug in slugs]
    lines = ["PLOT SPINE — every one of these must happen on the page, in this order:"]
    for beat in beats:
        marker = "  [PIVOTAL] " if beat.load_bearing else "  "
        causes = f" (this beat causes: {', '.join(beat.causes)})" if beat.causes else ""
        lines.append(f"{marker}{beat.id}: {beat.actor_role} — {beat.action} [{beat.outcome}]{causes}")
    if roles:
        lines.append("")
        lines.append("ROLES IN THIS SCENE (invent your own names; these are functions):")
        for role in roles:
            lines.append(f"  - {role.slug}")
    return "\n".join(lines)


def write_scene(
    beats: List[Beat],
    skeleton: StorySkeleton,
    pack: GenrePack,
    rolling_summary: str = "",
    scene_index: int = 0,
    scene_total: int = 1,
    missing: Optional[List[Beat]] = None,
) -> Scene:
    """One LLM call. `missing` re-asks for beats a previous attempt dropped."""
    parts = [pack.as_brief(), "", _render_spine(beats, skeleton)]
    if rolling_summary:
        parts += ["", "THE STORY SO FAR (continue from here; do not restate it):", rolling_summary]
    else:
        parts += ["", "This is the opening scene. Establish the world from nothing."]
    if scene_index == scene_total - 1:
        parts += ["", "This is the FINAL scene. The story ends here — land it, do not set up more."]

    prompt = "\n".join(parts)
    if missing:
        complaint = "\n".join(f"  - {b.id}: {b.action}" for b in missing)
        prompt = RETRY_PREFIX.format(missing=complaint) + "\n\n" + prompt

    from llm import structured  # deferred so --selftest needs no credentials

    return structured(TRANSFORM_SYSTEM, prompt, Scene, temperature=TRANSFORM_TEMPERATURE)


def transform(
    skeleton: StorySkeleton,
    pack: GenrePack,
    verbose: bool = False,
    on_progress: Optional[Callable[[int, int, str], None]] = None,
) -> str:
    """Drive the scenes and return the rewritten story.

    Retries a scene once when it drops a load-bearing beat, with the beat quoted,
    then moves on — a supporting beat is worth less than the wall-clock of a
    second retry, and the verifier will report it either way.

    `on_progress(done, total, note)` is called after each scene, so a long-running
    caller (the HTTP service) can report which scene it is on. Optional and
    additive: the CLI path is unchanged.
    """
    scenes = plan_scenes(skeleton)
    prose_parts: List[str] = []
    summary = ""

    for index, beats in enumerate(scenes):
        ids = ",".join(b.id for b in beats)
        if verbose:
            print(f"  scene {index + 1}/{len(scenes)} [{ids}]", end="", file=sys.stderr, flush=True)

        scene = write_scene(beats, skeleton, pack, summary, index, len(scenes))

        covered = set(scene.beats_covered)
        dropped = [b for b in beats if b.id not in covered and b.load_bearing]
        if dropped:
            if verbose:
                print(f" -> missing {','.join(b.id for b in dropped)}, re-asking", end="", file=sys.stderr)
            scene = write_scene(
                beats, skeleton, pack, summary, index, len(scenes), missing=dropped
            )
            covered = set(scene.beats_covered)
            dropped = [b for b in beats if b.id not in covered and b.load_bearing]

        if verbose:
            note = f"  ({len(scene.prose.split())}w)"
            if dropped:
                note += f"  STILL MISSING {','.join(b.id for b in dropped)}"
            print(note, file=sys.stderr)

        prose_parts.append(scene.prose.strip())
        summary = scene.summary_for_next

        if on_progress:
            note = f"scene {index + 1}/{len(scenes)}"
            if dropped:
                note += f" (missing {','.join(b.id for b in dropped)})"
            on_progress(index + 1, len(scenes), note)

    return "\n\n".join(prose_parts)


# --------------------------------------------------------------------------
# self-test: scene planning is pure Python, so it is checkable with no network
# --------------------------------------------------------------------------


def _beats(spec) -> StorySkeleton:
    from models import Role

    return StorySkeleton(
        logline="the protagonist wants a thing the gatekeeper controls",
        roles=[Role(slug="protagonist", name="A")],
        beats=[
            Beat(id=i, actor_role="protagonist", action=f"beat {i}", causes=[], outcome="status_quo", load_bearing=lb)
            for (i, lb) in spec
        ],
    )


def _selftest() -> int:
    def check(spec, expected, label):
        sk = _beats(spec)
        got = [[b.id for b in scene] for scene in plan_scenes(sk)]
        flat = [i for scene in got for i in scene]
        assert flat == [i for (i, _) in spec], f"{label}: beats reordered or lost: {got}"
        assert got == expected, f"{label}: got {got}, want {expected}"
        for scene in plan_scenes(sk):
            pivots = [b.id for b in scene if b.load_bearing]
            assert len(pivots) <= 1, f"{label}: scene carries two pivots {pivots}"
        print(f"  {label:<34} {got}")

    print("plan_scenes")
    check([("b1", False), ("b2", True), ("b3", False), ("b4", True)],
          [["b1", "b2"], ["b3", "b4"]], "cuts after each pivot")
    check([("b1", False), ("b2", False), ("b3", False), ("b4", False), ("b5", False)],
          [["b1", "b2", "b3"], ["b4", "b5"]], "no pivots -> max_beats chunks")
    check([("b1", True), ("b2", True), ("b3", True)],
          [["b1"], ["b2"], ["b3"]], "all pivots -> one each")
    check([("b1", True), ("b2", False)],
          [["b1", "b2"]], "trailing supporting beat joins previous")
    check([("b1", False)], [["b1"]], "single beat")

    print()
    print("genre packs")
    for name in available_packs():
        pack = load_pack(name)
        assert pack.taboo_moves and pack.obligatory_beats, name
        print(f"  {name:<12} {len(pack.obligatory_beats)} obligatory, {len(pack.taboo_moves)} taboo")

    print()
    print("scene planning OK")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rewrite a story in a target genre.")
    parser.add_argument("story", nargs="?", help="path to a story .txt")
    parser.add_argument("--genre", help=f"one of: {', '.join(available_packs())}")
    parser.add_argument("--selftest", action="store_true", help="scene planning, offline")
    parser.add_argument("--out", help="write the rewritten story here")
    args = parser.parse_args()

    if args.selftest:
        raise SystemExit(_selftest())
    if not args.story or not args.genre:
        parser.error("give a story and --genre, or --selftest")

    from extract import extract_clean

    print(f"extracting {args.story}", file=sys.stderr)
    sk, _ = extract_clean(Path(args.story).read_text(), verbose=True)
    print(f"transforming -> {args.genre}", file=sys.stderr)
    story = transform(sk, load_pack(args.genre), verbose=True)

    print(story)
    if args.out:
        Path(args.out).write_text(story)
        print(f"\nwrote {args.out}", file=sys.stderr)
