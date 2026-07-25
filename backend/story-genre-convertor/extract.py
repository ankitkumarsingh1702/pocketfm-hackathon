"""Stage 1: story -> StorySkeleton.

If extraction is mushy, everything downstream is mush. The lint below costs
zero tokens and catches the two failure modes that matter: leaked proper nouns
and leaked genre vocabulary. Either one means the transform stage won't be able
to move the story far, because the skeleton it's pinned to is already flavoured.
"""

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple

from llm import structured
from models import StorySkeleton

EXTRACT_SYSTEM = """You extract the genre-neutral causal skeleton of a story.

The skeleton will be used to rewrite the same story in a completely different \
genre — horror, romance, comedy, thriller, anime — while keeping the plot \
intact. Anything you leave in the skeleton is something the rewrite cannot \
change. So the skeleton must contain the plot and nothing else.

Five rules, in priority order:

1. NO PROPER NOUNS. No character names, no place names, no titles of objects. \
Refer to every character by their function slug. The only exception is the \
`name` field on a role, which exists precisely to hold the source name.

2. NO GENRE LANGUAGE. Do not write "dread", "haunting", "tender", "hilarious", \
"lurking", "confronts destiny", "a chill runs through". Write flat, functional \
prose. A beat should read like a line from a court transcript, not from a novel.

3. NO SENSORY DETAIL. No weather, no rooms, no objects described by appearance, \
no time of day. If a detail could be swapped for a different detail without \
changing who gets what, it does not belong in the skeleton.

4. HONEST CAUSAL EDGES. `causes` is not "what happens next". It is "what this \
beat makes possible". If beat B would still happen with beat A deleted, A does \
not cause B. Sparse and correct beats dense and wrong.

5. STRICT LOAD-BEARING FLAGS. A beat is load-bearing only if deleting it breaks \
a later beat or changes the ending. Escalations that repeat existing pressure, \
scene-setting, and reaction beats are not load-bearing.

Decompose, do not summarise. A 1000-word story usually has 8 to 15 beats. \
Preserve the order in which the reader encounters events, including the order \
of reveals — when information arrives is part of the plot."""

RETRY_PREFIX = """Your previous skeleton violated the extraction rules.

{complaint}

Produce the skeleton again. Keep the SAME beats, the SAME ids, the SAME causal \
edges, and the SAME load_bearing flags. Change only the wording of the fields \
that violated the rules, so they are abstract and genre-neutral. Do not add \
beats, remove beats, or re-order anything."""

# Words that mean a genre has leaked into the supposedly genre-neutral layer.
GENRE_WORDS = {
    # horror
    "dread", "haunt", "haunted", "haunting", "eerie", "sinister", "ominous",
    "terror", "terrifying", "ghost", "ghostly", "monstrous", "grotesque",
    "shudder", "chill", "lurk", "lurking", "creeping", "nightmare", "macabre",
    "unnatural", "cursed", "possessed", "blood-soaked", "spectral",
    # romance
    "tender", "yearning", "longing", "beloved", "passion", "passionate",
    "intimate", "swoon", "heartache", "heartbreak", "romantic", "lovers",
    "courtship", "infatuated", "smitten", "aching",
    # comedy
    "hilarious", "comic", "comical", "absurd", "farcical", "slapstick",
    "bumbling", "ridiculous", "hapless", "zany", "punchline", "gag",
    # thriller
    "pulse-pounding", "high-stakes", "deadly", "lethal", "conspiracy",
    "assassin", "manhunt", "ticking clock", "adrenaline", "relentless",
    "cat-and-mouse", "shadowy",
    # anime
    "senpai", "sensei", "nakama", "shonen", "tsundere", "chibi",
    "transformation sequence", "power level", "ultimate technique",
    "inner monologue", "destined rival",
    # generic literary flourish
    "fateful", "destiny", "soul", "heart-wrenching", "gut-wrenching",
    "spine", "raw emotion",
}

# Leading words that show up in functional role names — "the water regulator",
# "The board", "Her employer". Capitalisation alone doesn't disqualify them
# (they start the phrase), and matching one would flag every beat in the story.
NAME_NOISE = {"the", "a", "an", "his", "her", "its", "their", "our", "my", "your"}


def extract_skeleton(story: str, feedback: str = "") -> StorySkeleton:
    """One extraction call. `feedback` re-asks with a specific complaint."""
    prompt = story if not feedback else RETRY_PREFIX.format(complaint=feedback) + "\n\n" + story
    return structured(EXTRACT_SYSTEM, prompt, StorySkeleton)


def name_probes(name: str) -> List[str]:
    """The strings that would give this role's identity away if one leaked.

    The whole name, plus any token that reads as a proper noun — so "Devraj
    Iyer" is caught by a bare "Devraj". Roles are frequently named by function
    rather than by person ("the water regulator", "The second lawyer"), and
    those phrases have no proper noun to leak: taking their first token would
    put "the" on the watchlist and flag every beat in the story.
    """
    probes = [name] if len(name) > 2 else []
    for token in re.findall(r"[\w']+", name):
        if len(token) > 2 and token[0].isupper() and token.lower() not in NAME_NOISE:
            probes.append(token)
    return probes


def lint_skeleton(skeleton: StorySkeleton) -> List[str]:
    """Pure Python, zero tokens. Returns a list of complaints; empty means clean."""
    complaints: List[str] = []

    # Everything the model wrote, except the role names (which are allowed to be proper nouns).
    surfaces: List[Tuple[str, str]] = [("logline", skeleton.logline)]
    for beat in skeleton.beats:
        surfaces.append((f"beat {beat.id} action", beat.action))
    for role in skeleton.roles:
        surfaces.append((f"role slug '{role.slug}'", role.slug))

    # 1. Leaked character names.
    for label, text in surfaces:
        lowered = text.lower()
        for name in skeleton.role_names:
            for probe in name_probes(name):
                if probe.lower() in lowered:
                    complaints.append(f"{label} contains the character name '{probe}': {text!r}")
                    break

    # 2. Leaked genre vocabulary.
    for label, text in surfaces:
        lowered = text.lower()
        hits = sorted({w for w in GENRE_WORDS if w in lowered})
        if hits:
            complaints.append(f"{label} uses genre-loaded language {hits}: {text!r}")

    # 3. Structural sanity — cheap to check, expensive to discover later.
    slugs = {r.slug for r in skeleton.roles}
    ids = [b.id for b in skeleton.beats]
    for beat in skeleton.beats:
        if beat.actor_role not in slugs:
            complaints.append(f"beat {beat.id} has actor_role '{beat.actor_role}' not present in roles")
        for target in beat.causes:
            if target not in ids:
                complaints.append(f"beat {beat.id} causes unknown beat id '{target}'")
    if len(set(ids)) != len(ids):
        complaints.append("duplicate beat ids")
    if not skeleton.load_bearing_ids:
        complaints.append("no beats flagged load_bearing — the verifier has nothing to weigh")

    return sorted(set(complaints))


def extract_clean(story: str, verbose: bool = False) -> Tuple[StorySkeleton, List[str]]:
    """Extract, lint, and re-ask once if it leaked.

    Returns (skeleton, remaining_complaints). Remaining complaints after the
    retry are surfaced rather than raised — a slightly dirty skeleton is still
    usable, you just want to know.
    """
    skeleton = extract_skeleton(story)
    complaints = lint_skeleton(skeleton)
    if not complaints:
        return skeleton, []

    if verbose:
        print(f"  lint failed ({len(complaints)}), re-asking once", file=sys.stderr)

    feedback = "\n".join(f"- {c}" for c in complaints)
    skeleton = extract_skeleton(story, feedback=feedback)
    return skeleton, lint_skeleton(skeleton)


def print_skeleton(skeleton: StorySkeleton) -> None:
    print(f"LOGLINE  {skeleton.logline}")
    print("ROLES")
    for role in skeleton.roles:
        print(f"  {role.slug:<22} = {role.name}")
    print(f"BEATS ({len(skeleton.beats)}, {len(skeleton.load_bearing_ids)} load-bearing)")
    for beat in skeleton.beats:
        marker = "*" if beat.load_bearing else " "
        causes = f"  -> {','.join(beat.causes)}" if beat.causes else ""
        print(f" {marker}{beat.id:<4} [{beat.outcome:<10}] {beat.actor_role}: {beat.action}{causes}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract a genre-neutral skeleton from a story.")
    parser.add_argument("story", help="path to a story .txt")
    parser.add_argument(
        "--out",
        help="also write the skeleton as JSON here, so verify.py can consume it",
    )
    args = parser.parse_args()

    text = Path(args.story).read_text()
    sk, remaining = extract_clean(text, verbose=True)
    print_skeleton(sk)
    if args.out:
        Path(args.out).write_text(sk.model_dump_json(indent=2))
        print(f"\nwrote {args.out}", file=sys.stderr)
    if remaining:
        print("\nLINT (after one retry):", file=sys.stderr)
        for c in remaining:
            print(f"  - {c}", file=sys.stderr)
    else:
        print("\nlint: clean", file=sys.stderr)
