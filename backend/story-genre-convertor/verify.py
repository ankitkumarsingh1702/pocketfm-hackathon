"""Stage 3: did the plot survive?

Re-extract a skeleton from the rewritten story, align it beat-for-beat against
the source skeleton, and score the result. The alignment is the only LLM call —
judging "same causal function" is a language problem. The scoring is
deterministic Python, so the number is reproducible and auditable.

Run `python verify.py --selftest` to exercise the scoring math with no API key.
"""

import argparse
import json
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from models import Beat, Role, StorySkeleton

# 60% of the score is "did the load-bearing beats survive", because that is the
# claim we are actually making. The other two components stop a rewrite from
# scoring well by preserving the spine while shredding everything around it.
W_LOAD_BEARING = 0.60
W_ALL_BEATS = 0.20
W_EDGES = 0.20

# The alignment call is the only judgement in the pipeline and it is not
# reproducible on its own, so it is run several times and voted. Odd numbers
# only — an even count makes "strict majority" needlessly harsh.
ALIGN_VOTES = int(os.environ.get("ALIGN_VOTES", "3"))


class BeatMatch(BaseModel):
    source_id: str = Field(description="Id of the beat in the SOURCE skeleton.")
    candidate_ids: List[str] = Field(
        description=(
            "Ids of the CANDIDATE beats that TOGETHER serve this source beat's "
            "causal function. Usually exactly one. Use several when the rewrite "
            "dramatised one source beat across consecutive beats — an offer and "
            "its acceptance written as two beats still serve one source beat. "
            "Use an empty list when nothing in the candidate serves this function. "
            "The same candidate id MAY appear under two different source beats, "
            "when the rewrite merged them into a single beat."
        )
    )
    same_causal_function: bool = Field(
        description=(
            "True only if those candidate beats, taken together, do the same "
            "structural work: the same role acts, the same kind of thing is won "
            "or lost or revealed, and the story is in the same position "
            "afterwards. False if you had to stretch."
        )
    )
    note: str = Field(
        description="One short clause justifying the verdict. Empty string if the match is obvious."
    )


class Alignment(BaseModel):
    matches: List[BeatMatch] = Field(
        description="Exactly one entry per beat in the source skeleton, in source order."
    )


ALIGN_SYSTEM = """You compare two story skeletons: a SOURCE and a CANDIDATE \
produced by rewriting the same story in a different genre.

Your job is to decide, for each source beat, whether the candidate contains a \
beat doing the same causal work.

Score FUNCTION, not surface. The rewrite was supposed to change the setting, \
the names, the imagery, the nature of the threat, and the emotional register. \
None of that is a failure. A betrayal by a business partner and a betrayal by a \
ghost are the same beat. A door that is locked and a spell that is sealed are \
the same obstacle.

What IS a failure:
- the beat is simply absent from the candidate
- a different role performs it
- the outcome flips (a failure became a success, a reveal never lands)
- the beat now happens before something it used to depend on

Be strict rather than generous. If you find yourself constructing an argument \
for why two beats are "sort of" equivalent, they are not. A false match is far \
more damaging than a missed one, because it makes a broken rewrite look intact.

GRANULARITY IS NOT DRIFT. The two skeletons were decomposed independently, so \
they will not have cut the story at the same points. That is not a failure, and \
you must not score it as one:
- If the rewrite dramatised one source beat as two or three consecutive beats, \
list all of them for that source beat. An offer and its acceptance written \
separately still serve the one source beat that had them together.
- If the rewrite folded two source beats into one, name that same candidate beat \
under both source beats. Both are genuinely served by it.
Judge whether the causal work got done, not whether it got done in the same \
number of pieces.

Produce exactly one match entry per source beat, in source order."""


def _render(skeleton: StorySkeleton, label: str) -> str:
    lines = [f"=== {label} ===", f"logline: {skeleton.logline}", "beats:"]
    for beat in skeleton.beats:
        marker = "LOAD-BEARING" if beat.load_bearing else "supporting"
        causes = f" causes={','.join(beat.causes)}" if beat.causes else ""
        lines.append(
            f"  {beat.id}: [{beat.outcome}] [{marker}] {beat.actor_role}: {beat.action}{causes}"
        )
    return "\n".join(lines)


def align_once(source: StorySkeleton, candidate: StorySkeleton) -> Alignment:
    """One alignment call."""
    from llm import structured  # imported here so --selftest needs no credentials path

    prompt = _render(source, "SOURCE") + "\n\n" + _render(candidate, "CANDIDATE")
    return structured(ALIGN_SYSTEM, prompt, Alignment)


def merge_votes(source: StorySkeleton, ballots: List[Alignment]) -> Alignment:
    """Combine independent alignments into one, by majority per source beat.

    A source beat counts as matched only if a strict majority of ballots say so.
    Deterministic given the ballots — no model involved, so it is selftestable.
    """
    threshold = len(ballots) // 2 + 1
    by_source: Dict[str, List[BeatMatch]] = {}
    for ballot in ballots:
        for match in ballot.matches:
            by_source.setdefault(match.source_id, []).append(match)

    merged: List[BeatMatch] = []
    for beat in source.beats:
        entries = by_source.get(beat.id, [])
        yes = [e for e in entries if e.same_causal_function and e.candidate_ids]
        if len(yes) < threshold:
            merged.append(
                BeatMatch(
                    source_id=beat.id,
                    candidate_ids=[],
                    same_causal_function=False,
                    note=f"{len(yes)}/{len(ballots)} matched",
                )
            )
            continue
        # Keep the candidate ids the agreeing ballots actually named. Ids only a
        # minority saw are dropped, unless that would leave nothing at all.
        tally: Dict[str, int] = {}
        for entry in yes:
            for cid in entry.candidate_ids:
                tally[cid] = tally.get(cid, 0) + 1
        kept = [cid for cid, n in tally.items() if n >= threshold]
        if not kept:
            kept = [max(tally, key=lambda c: tally[c])]
        merged.append(
            BeatMatch(
                source_id=beat.id,
                candidate_ids=kept,
                same_causal_function=True,
                note=f"{len(yes)}/{len(ballots)} matched",
            )
        )
    return Alignment(matches=merged)


def align(source: StorySkeleton, candidate: StorySkeleton, votes: int = ALIGN_VOTES) -> Alignment:
    """Align by majority of `votes` independent calls.

    One call is not reproducible. The same two skeletons scored 67.73% and 92.88%
    on separate runs at temperature 0, because the model is only near-deterministic
    — identical prompts can route differently. Averaging ballots turns the judge
    from an instrument with a 25-point swing into one worth reporting.
    """
    if votes <= 1:
        return align_once(source, candidate)
    return merge_votes(source, [align_once(source, candidate) for _ in range(votes)])


def score(
    source: StorySkeleton, candidate: StorySkeleton, alignment: Alignment
) -> Dict[str, object]:
    """Deterministic. No model involved.

    Weighted: 60% load-bearing recall, 20% all-beat recall, 20% causal edge
    recall.

    Matching is many-to-many on purpose. Two independent decompositions of the
    same story will not cut it in the same places, and an earlier one-to-one rule
    punished that as if it were plot damage: 14 source beats against 8 candidate
    beats capped the score at 8/14 before any judgement happened. A source beat
    split across several candidate beats is still delivered; two source beats
    folded into one candidate beat are both still delivered.
    """
    matched: Dict[str, List[str]] = {}
    for m in alignment.matches:
        if not m.same_causal_function or not m.candidate_ids:
            continue
        if source.beat(m.source_id) is None:
            continue
        ids = [c for c in m.candidate_ids if candidate.beat(c) is not None]
        if ids:
            matched[m.source_id] = ids

    # 1. load-bearing recall
    lb_ids = source.load_bearing_ids
    lb_kept = [i for i in lb_ids if i in matched]

    # 2. all-beat recall
    all_ids = [b.id for b in source.beats]
    all_kept = [i for i in all_ids if i in matched]

    # 3. causal edge recall
    cand_edges = set(candidate.causal_edges)
    src_edges = source.causal_edges

    def edge_survives(s: str, t: str) -> bool:
        """Did the link between two source beats make it into the candidate?"""
        if s not in matched or t not in matched:
            return False
        heads, tails = set(matched[s]), set(matched[t])
        # Both source beats landed inside one candidate beat: the rewrite merged
        # them, so the causal link is internal to that beat rather than broken.
        if heads & tails:
            return True
        return any((h, t2) in cand_edges for h in heads for t2 in tails)

    edges_kept = [(s, t) for (s, t) in src_edges if edge_survives(s, t)]

    components: List[Tuple[str, float, int, int]] = [
        ("load_bearing_recall", W_LOAD_BEARING, len(lb_kept), len(lb_ids)),
        ("beat_recall", W_ALL_BEATS, len(all_kept), len(all_ids)),
        ("edge_recall", W_EDGES, len(edges_kept), len(src_edges)),
    ]

    # Renormalise over the components that have something to measure, so a
    # story with no causal edges is not silently rewarded or punished.
    live_weight = sum(w for _, w, _, d in components if d > 0)
    detail: Dict[str, object] = {}
    total = 0.0
    for name, weight, kept, denom in components:
        value = (kept / denom) if denom else None
        detail[name] = None if value is None else round(value, 4)
        detail[f"{name}_counts"] = f"{kept}/{denom}"
        if denom and live_weight:
            total += (weight / live_weight) * value

    detail["fidelity"] = round(total, 4)
    detail["missing_load_bearing"] = [i for i in lb_ids if i not in matched]
    detail["broken_edges"] = [f"{s}->{t}" for (s, t) in src_edges if (s, t) not in edges_kept]
    return detail


def verify(source: StorySkeleton, candidate: StorySkeleton) -> Dict[str, object]:
    """Skeleton against skeleton. Kept for calibration, where there is no prose."""
    return score(source, candidate, align(source, candidate))


# ---------------------------------------------------------------------------
# Prose-based scoring — the primary measure
# ---------------------------------------------------------------------------
#
# Judging a rewrite by re-extracting a skeleton from it and comparing skeletons
# compares paraphrase to paraphrase, and extraction is lossy in exactly the way
# that matters. In the corpus benchmark, `understudy -> comedy` scored 23.81%
# that way; asked directly, 8 of its 9 beats were on the page. The re-extraction
# had rendered "chooses not to deliver the message" as "asks the organizer if
# the superior is absent" — true, and missing the omission that was the point.
#
# So the source beats are now checked against the rewritten PROSE. Same three
# components, same weights, same output shape; the evidence underneath is just
# no longer second-hand.


def score_prose(
    source: StorySkeleton,
    delivery: "DeliveryReport",
    links: "LinkReport",
) -> Dict[str, object]:
    """Deterministic. Same 60/20/20 as `score`, judged against the prose."""
    from delivery import delivered_ids, preserved_edges

    kept = set(delivered_ids(delivery, source.beats))

    lb_ids = source.load_bearing_ids
    all_ids = [b.id for b in source.beats]
    src_edges = source.causal_edges
    edges_kept = preserved_edges(links, src_edges)

    components = [
        ("load_bearing_recall", W_LOAD_BEARING, len([i for i in lb_ids if i in kept]), len(lb_ids)),
        ("beat_recall", W_ALL_BEATS, len([i for i in all_ids if i in kept]), len(all_ids)),
        ("edge_recall", W_EDGES, len(edges_kept), len(src_edges)),
    ]

    live_weight = sum(w for _, w, _, d in components if d > 0)
    detail: Dict[str, object] = {}
    total = 0.0
    for name, weight, count, denom in components:
        value = (count / denom) if denom else None
        detail[name] = None if value is None else round(value, 4)
        detail[f"{name}_counts"] = f"{count}/{denom}"
        if denom and live_weight:
            total += (weight / live_weight) * value

    detail["fidelity"] = round(total, 4)
    detail["missing_load_bearing"] = [i for i in lb_ids if i not in kept]
    detail["broken_edges"] = [f"{s}->{t}" for (s, t) in src_edges if (s, t) not in set(edges_kept)]
    # Why each beat failed, which the skeleton comparison could never say.
    detail["beat_notes"] = {
        v.beat_id: v.note for v in delivery.verdicts if not v.delivered and v.note
    }
    detail["method"] = "prose"
    return detail


def merge_delivery_votes(source: StorySkeleton, ballots: List["DeliveryReport"]) -> "DeliveryReport":
    """Majority vote over delivery ballots. Pure, so it is selftestable."""
    from delivery import BeatVerdict, DeliveryReport

    threshold = len(ballots) // 2 + 1
    merged = []
    for beat in source.beats:
        votes = [v for b in ballots for v in b.verdicts if v.beat_id == beat.id]
        yes = [v for v in votes if v.delivered]
        if len(yes) >= threshold:
            merged.append(
                BeatVerdict(
                    beat_id=beat.id,
                    delivered=True,
                    position=sorted(v.position for v in yes)[len(yes) // 2],
                    note=f"{len(yes)}/{len(ballots)} found it",
                )
            )
        else:
            # Carry a dissenting reason forward — "wrong actor" is worth keeping
            # even when the vote goes against delivery.
            note = next((v.note for v in votes if not v.delivered and v.note), "")
            merged.append(
                BeatVerdict(
                    beat_id=beat.id,
                    delivered=False,
                    position=0,
                    note=f"{len(yes)}/{len(ballots)} found it" + (f" — {note}" if note else ""),
                )
            )
    return DeliveryReport(verdicts=merged)


def merge_link_votes(edges: List[tuple], ballots: List["LinkReport"]) -> "LinkReport":
    """Majority vote over causal-link ballots."""
    from delivery import LinkReport, LinkVerdict

    threshold = len(ballots) // 2 + 1
    merged = []
    for source_id, target_id in edges:
        votes = [
            v
            for b in ballots
            for v in b.verdicts
            if v.source_id == source_id and v.target_id == target_id
        ]
        yes = [v for v in votes if v.preserved]
        note = next((v.note for v in votes if not v.preserved and v.note), "")
        merged.append(
            LinkVerdict(
                source_id=source_id,
                target_id=target_id,
                preserved=len(yes) >= threshold,
                note=f"{len(yes)}/{len(ballots)}" + (f" — {note}" if note and len(yes) < threshold else ""),
            )
        )
    return LinkReport(verdicts=merged)


def verify_prose(
    source: StorySkeleton,
    prose: str,
    votes: int = ALIGN_VOTES,
    on_progress: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, object]:
    """Score a rewrite directly against the source skeleton. The primary path.

    `on_progress(done, total, note)` fires after each ballot. This stage is
    `votes * 2` model calls at the end of a five-minute job, so a caller with no
    visibility into it looks stalled exactly when the user is least patient.
    Optional and additive: the CLI path is unchanged.
    """
    from delivery import check_delivery, check_links

    edges = source.causal_edges
    total = 2 if votes <= 1 else votes * 2
    done = 0

    def tick(note: str) -> None:
        nonlocal done
        done += 1
        if on_progress:
            on_progress(done, total, note)

    if votes <= 1:
        delivery = check_delivery(prose, source.beats)
        tick("checked beats against the page")
        links = check_links(prose, edges, source.beats)
        tick("checked causal links")
        return score_prose(source, delivery, links)

    delivery_ballots = []
    for round_number in range(1, votes + 1):
        delivery_ballots.append(check_delivery(prose, source.beats))
        tick(f"beat check {round_number}/{votes}")

    link_ballots = []
    for round_number in range(1, votes + 1):
        link_ballots.append(check_links(prose, edges, source.beats))
        tick(f"causal-link check {round_number}/{votes}")

    delivery = merge_delivery_votes(source, delivery_ballots)
    links = merge_link_votes(edges, link_ballots)
    return score_prose(source, delivery, links)


def print_report(result: Dict[str, object], label: str = "") -> None:
    head = f"fidelity {result['fidelity']:.2%}"
    if label:
        head = f"{label}: {head}"
    print(head)
    for key in ("load_bearing_recall", "beat_recall", "edge_recall"):
        counts = result[f"{key}_counts"]
        val = result[key]
        shown = "n/a " if val is None else f"{val:.2%}"
        print(f"  {key:<20} {shown:>8}  ({counts})")
    if result["missing_load_bearing"]:
        print(f"  dropped load-bearing beats: {', '.join(result['missing_load_bearing'])}")
    if result["broken_edges"]:
        print(f"  broken causal edges: {', '.join(result['broken_edges'])}")


# --------------------------------------------------------------------------
# self-test: exercises the scoring math with no API key and no network
# --------------------------------------------------------------------------


def _toy(beat_specs) -> StorySkeleton:
    return StorySkeleton(
        logline="the protagonist wants a thing the gatekeeper controls",
        roles=[Role(slug="protagonist", name="A"), Role(slug="gatekeeper", name="B")],
        beats=[
            Beat(
                id=i,
                actor_role=r,
                action=f"beat {i}",
                causes=c,
                outcome=o,
                load_bearing=lb,
            )
            for (i, r, c, o, lb) in beat_specs
        ],
    )


def _selftest() -> int:
    chain = [
        ("b1", "protagonist", ["b2"], "status_quo", False),
        ("b2", "gatekeeper", ["b3"], "failure", True),
        ("b3", "protagonist", ["b4"], "reveal", True),
        ("b4", "gatekeeper", [], "reversal", True),
    ]
    src = _toy(chain)

    # Case 1: perfect rewrite — every beat present, chain intact.
    perfect = _toy(chain)
    align_all = Alignment(
        matches=[
            BeatMatch(source_id=i, candidate_ids=[i], same_causal_function=True, note="")
            for (i, _, _, _, _) in chain
        ]
    )
    r1 = score(src, perfect, align_all)
    print_report(r1, "perfect rewrite")
    assert r1["fidelity"] == 1.0, r1

    # Case 2: the middle load-bearing beat is dropped, so the chain has a hole.
    holed = _toy([s for s in chain if s[0] != "b3"])
    align_hole = Alignment(
        matches=[
            BeatMatch(
                source_id=i,
                candidate_ids=[] if i == "b3" else [i],
                same_causal_function=(i != "b3"),
                note="dropped" if i == "b3" else "",
            )
            for (i, _, _, _, _) in chain
        ]
    )
    r2 = score(src, holed, align_hole)
    print()
    print_report(r2, "middle beat dropped")
    # Dropping one beat kills both edges touching it; b1->b2 survives.
    assert r2["broken_edges"] == ["b2->b3", "b3->b4"], r2
    assert r2["edge_recall"] == round(1 / 3, 4), r2
    assert r2["missing_load_bearing"] == ["b3"], r2
    assert 0.60 < r2["fidelity"] < 0.65, r2

    # Case 3: the spine survives but the connective tissue is shredded. Should
    # still score well, because that is exactly what a genre rewrite does.
    thin = _toy([s for s in chain if s[0] != "b1"])
    align_thin = Alignment(
        matches=[
            BeatMatch(
                source_id=i,
                candidate_ids=[] if i == "b1" else [i],
                same_causal_function=(i != "b1"),
                note="",
            )
            for (i, _, _, _, _) in chain
        ]
    )
    r3 = score(src, thin, align_thin)
    print()
    print_report(r3, "supporting beat dropped")
    assert r3["load_bearing_recall"] == 1.0, r3
    assert r3["fidelity"] > 0.85, r3

    # Case 4: the rewrite MERGED b2 and b3 into one beat. Same plot, coarser
    # decomposition. Under the old one-to-one rule b3 was scored as dropped and
    # two edges as broken; both source beats are genuinely served here.
    merged = _toy([
        ("c1", "protagonist", ["c2"], "status_quo", False),
        ("c2", "gatekeeper", ["c3"], "failure", True),   # covers b2 AND b3
        ("c3", "gatekeeper", [], "reversal", True),
    ])
    align_merged = Alignment(
        matches=[
            BeatMatch(source_id="b1", candidate_ids=["c1"], same_causal_function=True, note=""),
            BeatMatch(source_id="b2", candidate_ids=["c2"], same_causal_function=True, note="merged"),
            BeatMatch(source_id="b3", candidate_ids=["c2"], same_causal_function=True, note="merged"),
            BeatMatch(source_id="b4", candidate_ids=["c3"], same_causal_function=True, note=""),
        ]
    )
    r4 = score(src, merged, align_merged)
    print()
    print_report(r4, "two beats merged into one")
    assert r4["fidelity"] == 1.0, r4
    assert r4["broken_edges"] == [], r4  # b2->b3 is internal to c2, not broken

    # Case 5: the rewrite SPLIT b3 across two beats. Also not plot damage.
    split = _toy([
        ("c1", "protagonist", ["c2"], "status_quo", False),
        ("c2", "gatekeeper", ["c3"], "failure", True),
        ("c3", "protagonist", ["c4"], "reveal", True),    # b3, first half
        ("c4", "protagonist", ["c5"], "reveal", True),    # b3, second half
        ("c5", "gatekeeper", [], "reversal", True),
    ])
    align_split = Alignment(
        matches=[
            BeatMatch(source_id="b1", candidate_ids=["c1"], same_causal_function=True, note=""),
            BeatMatch(source_id="b2", candidate_ids=["c2"], same_causal_function=True, note=""),
            BeatMatch(source_id="b3", candidate_ids=["c3", "c4"], same_causal_function=True, note="split"),
            BeatMatch(source_id="b4", candidate_ids=["c5"], same_causal_function=True, note=""),
        ]
    )
    r5 = score(src, split, align_split)
    print()
    print_report(r5, "one beat split in two")
    assert r5["fidelity"] == 1.0, r5
    assert r5["broken_edges"] == [], r5  # b3->b4 survives as c4->c5

    # Case 6: majority voting over disagreeing ballots.
    print()
    print("majority voting")
    def ballot(matched_ids):
        return Alignment(matches=[
            BeatMatch(
                source_id=i,
                candidate_ids=[i] if i in matched_ids else [],
                same_causal_function=i in matched_ids,
                note="",
            )
            for (i, _, _, _, _) in chain
        ])

    # b1 seen by all three, b2 by two, b3 by one, b4 by none.
    voted = merge_votes(src, [
        ballot({"b1", "b2", "b3"}),
        ballot({"b1", "b2"}),
        ballot({"b1"}),
    ])
    verdicts = {m.source_id: m.same_causal_function for m in voted.matches}
    assert verdicts == {"b1": True, "b2": True, "b3": False, "b4": False}, verdicts
    for m in voted.matches:
        print(f"  {m.source_id}  {'matched' if m.same_causal_function else 'dropped':<8} {m.note}")

    # A unanimous set of ballots must reproduce a single ballot exactly.
    unanimous = merge_votes(src, [align_all, align_all, align_all])
    assert score(src, perfect, unanimous)["fidelity"] == 1.0

    print()
    print("scoring math OK")
    return 0


def _load(path: str) -> StorySkeleton:
    return StorySkeleton.model_validate_json(Path(path).read_text())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify a rewrite preserved the plot.")
    parser.add_argument("--selftest", action="store_true", help="run scoring math offline")
    parser.add_argument("source", nargs="?", help="path to source skeleton JSON")
    parser.add_argument("candidate", nargs="?", help="path to candidate skeleton JSON")
    parser.add_argument("--json", action="store_true", help="emit the raw result dict")
    args = parser.parse_args()

    if args.selftest:
        raise SystemExit(_selftest())

    if not args.source or not args.candidate:
        parser.error("give two skeleton JSON paths, or --selftest")

    result = verify(_load(args.source), _load(args.candidate))
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_report(result)
