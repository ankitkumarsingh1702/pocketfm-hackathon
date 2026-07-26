"""Did the scene actually deliver its beats? Ask something other than the writer.

`Scene.beats_covered` is the generator grading its own homework, and the corpus
benchmark showed it failing twice in eleven runs, both times confidently:

  swap -> romance        opened at what should have been beat 7. The first five
                         beats were narrated as recollection, not dramatised.
                         Claimed: all. Delivered: none of them.
  understudy -> comedy   inverted the protagonist's guilt — she declines to lie
                         rather than lying — and reported the beat as covered.

Neither triggered the retry, because the retry consults the same self-report.
The independent re-extraction at the end caught both, but by then the whole
story was written and the cost of fixing it was a full re-run.

So: a separate call reads the prose cold, without being told what the writer
believed, and judges what is on the page. Same principle as the verifier, moved
earlier and made local. The check costs one call per scene and saves a rewrite.

    python delivery.py --selftest        # merge logic, no credentials
"""

import os
from typing import List, Optional

from pydantic import BaseModel, Field

from models import Beat

# Ballots per in-flight delivery check. One judgment is not reproducible — the
# same comparison has scored 68% and 93% on different runs — and here the
# asymmetry is sharp: a false "delivered" ships a broken pivot silently, a false
# "missing" merely costs one retry. So the gate votes, and disagreement resolves
# against the scene.
DELIVERY_VOTES = int(os.environ.get("DELIVERY_VOTES", "2"))

CHECK_SYSTEM = """You are given a passage of prose and a list of plot events.

For each event, decide whether it actually HAPPENS in this passage.

An event happens only if a reader watching the passage would see it occur. \
Apply that strictly:

- Dramatised on the page: YES. The characters do it, here, now.
- Referred to as something that happened earlier, in summary or memory or \
dialogue about the past: NO. Recollection is not occurrence.
- Set up, implied, foreshadowed, or about to happen: NO.
- Happens, but a different person does it than the event names: NO.
- Happens, but the outcome is inverted — the event says the actor refuses and \
the passage has them accept, or the event says they deceive and the passage has \
them tell the truth: NO. Say so in the note.

The prose is a genre rewrite, so surface details will not match: names, setting, \
objects, and the physical nature of everything are expected to be different. \
Judge the event, not its costume. A withheld document and a withheld confession \
are the same withholding.

Be strict. A false YES here lets a broken scene through, and the error is only \
found after the whole story is written."""


class BeatVerdict(BaseModel):
    beat_id: str = Field(description="The id of the event being judged.")
    delivered: bool = Field(
        description="True only if the event is dramatised on the page in this passage."
    )
    position: int = Field(
        0,
        description=(
            "Where this event occurs relative to the others you found: 1 for the "
            "earliest, 2 for the next, and so on. Use 0 when it is not delivered."
        ),
    )
    note: str = Field(
        description=(
            "One short clause. If not delivered, say which failure it was: absent, "
            "only recalled, wrong actor, or outcome inverted."
        )
    )


class DeliveryReport(BaseModel):
    verdicts: List[BeatVerdict] = Field(description="Exactly one per event given, in order.")


LINKS_SYSTEM = """You are given a passage of prose and a list of causal links \
between events in it.

For each link "A leads to B", decide whether the passage makes that connection \
legible: would a reader understand that B happens BECAUSE A happened?

A link is preserved when:
- both events occur in the passage, and
- B follows A, and
- the passage gives the reader reason to connect them — consequence, motive, or \
plain sequence where the causation is obvious.

A link is broken when:
- either event is absent,
- B happens before A,
- both occur but nothing connects them; B would have happened anyway,
- something else in the passage now causes B instead.

The prose is a genre rewrite, so the mechanism will look different — a letter \
may have become a rumour, a lock may have become a vow. Judge whether the \
causation survives, not whether the machinery matches.

Be strict. A chain that has quietly lost a link still reads well, which is \
exactly why it needs checking."""


class LinkVerdict(BaseModel):
    source_id: str = Field(description="Id of the causing event.")
    target_id: str = Field(description="Id of the caused event.")
    preserved: bool = Field(description="True only if the passage makes the causation legible.")
    note: str = Field(description="One short clause. If broken, say why.")


class LinkReport(BaseModel):
    verdicts: List[LinkVerdict] = Field(description="Exactly one per link given, in order.")


def _render(beats: List[Beat]) -> str:
    lines = ["EVENTS — decide for each whether it happens in the passage:"]
    for beat in beats:
        lines.append(f"  {beat.id}: {beat.actor_role} — {beat.action} [{beat.outcome}]")
    return "\n".join(lines)


def check_delivery(prose: str, beats: List[Beat], temperature: float = 0.0) -> DeliveryReport:
    """One call. Deliberately not told what the writer claimed."""
    from llm import structured  # deferred so --selftest needs no credentials

    prompt = f"{_render(beats)}\n\nPASSAGE:\n{prose}"
    return structured(CHECK_SYSTEM, prompt, DeliveryReport, temperature=temperature)


def merge_delivery(
    ballots: List[DeliveryReport], beats: List[Beat], threshold: Optional[int] = None
) -> DeliveryReport:
    """Merge independent ballots into one report. Pure, so it is selftestable.

    A beat counts delivered when at least `threshold` ballots found it on the
    page; the default is ALL of them — the strict form the in-flight gate wants,
    where any doubt buys a retry. Final measurement passes a majority threshold
    instead, so one stray "no" cannot report a delivered pivot as dropped. A
    ballot that returned no verdict for a beat counts as a no: silence is not
    consent.
    """
    need = len(ballots) if threshold is None else max(1, min(threshold, len(ballots)))
    verdicts: List[BeatVerdict] = []
    for beat in beats:
        found = [v for ballot in ballots for v in ballot.verdicts if v.beat_id == beat.id]
        yes = [v for v in found if v.delivered]
        tally = f"{len(yes)}/{len(ballots)} ballots"
        if len(yes) >= need:
            verdicts.append(
                BeatVerdict(beat_id=beat.id, delivered=True, position=yes[0].position, note=tally)
            )
        else:
            reasons = [v.note for v in found if not v.delivered and v.note]
            why = reasons[0] if reasons else ("no ballot returned a verdict" if not found else "")
            note = f"{why} ({tally})" if why else tally
            verdicts.append(BeatVerdict(beat_id=beat.id, delivered=False, position=0, note=note))
    return DeliveryReport(verdicts=verdicts)


def check_delivery_voted(
    prose: str,
    beats: List[Beat],
    votes: int = DELIVERY_VOTES,
    threshold: Optional[int] = None,
) -> DeliveryReport:
    """`votes` independent ballots, merged by `merge_delivery`.

    The first ballot runs at temperature 0 as before; the extra ballots run
    warmer, because identical deterministic reads are correlated and voting
    correlated ballots buys nothing.
    """
    if votes <= 1:
        return check_delivery(prose, beats)
    from concurrent.futures import ThreadPoolExecutor

    temps = [0.0] + [0.5] * (votes - 1)
    with ThreadPoolExecutor(max_workers=votes) as pool:
        ballots = list(pool.map(lambda t: check_delivery(prose, beats, temperature=t), temps))
    return merge_delivery(ballots, beats, threshold)


def check_links(prose: str, edges: List[tuple], beats: List[Beat]) -> LinkReport:
    """One call, judging whether each causal link survived into the prose."""
    from llm import structured

    if not edges:
        return LinkReport(verdicts=[])

    by_id = {b.id: b for b in beats}
    lines = ["CAUSAL LINKS — decide for each whether the passage makes the causation legible:"]
    for source_id, target_id in edges:
        head, tail = by_id.get(source_id), by_id.get(target_id)
        if head is None or tail is None:
            continue
        lines.append(f"  {source_id} -> {target_id}")
        lines.append(f"      {source_id}: {head.action}")
        lines.append(f"      {target_id}: {tail.action}")

    prompt = "\n".join(lines) + f"\n\nPASSAGE:\n{prose}"
    return structured(LINKS_SYSTEM, prompt, LinkReport, temperature=0)


def preserved_edges(report: LinkReport, edges: List[tuple]) -> List[tuple]:
    """Links the check confirmed, restricted to the ones actually asked about."""
    asked = set(edges)
    return [
        (v.source_id, v.target_id)
        for v in report.verdicts
        if v.preserved and (v.source_id, v.target_id) in asked
    ]


def delivered_ids(report: DeliveryReport, beats: List[Beat]) -> List[str]:
    """Ids the check confirmed, restricted to the beats actually assigned."""
    assigned = {b.id for b in beats}
    return [v.beat_id for v in report.verdicts if v.delivered and v.beat_id in assigned]


def undelivered(report: DeliveryReport, beats: List[Beat], load_bearing_only: bool = False) -> List[Beat]:
    """The beats to re-ask for. A verdict missing entirely counts as undelivered."""
    confirmed = set(delivered_ids(report, beats))
    missing = [b for b in beats if b.id not in confirmed]
    return [b for b in missing if b.load_bearing] if load_bearing_only else missing


def reconcile(claimed: List[str], report: DeliveryReport, beats: List[Beat]) -> List[str]:
    """Beats the writer claimed that the check could not find.

    Recorded rather than acted on: it is the measurement that tells you whether
    self-report is worth anything, and right now the answer is no.
    """
    confirmed = set(delivered_ids(report, beats))
    return sorted(set(claimed) - confirmed)


# --------------------------------------------------------------------------
# self-test: the merge logic is pure, so it runs with no credentials
# --------------------------------------------------------------------------


def _selftest() -> int:
    def beat(bid: str, load_bearing: bool = True) -> Beat:
        return Beat(
            id=bid,
            actor_role="protagonist",
            action=f"the protagonist does {bid}",
            causes=[],
            outcome="status_quo",
            load_bearing=load_bearing,
        )

    beats = [beat("b1"), beat("b2"), beat("b3", load_bearing=False)]

    def report(**delivered) -> DeliveryReport:
        return DeliveryReport(
            verdicts=[
                BeatVerdict(beat_id=bid, delivered=value, note="")
                for bid, value in delivered.items()
            ]
        )

    print("all delivered")
    full = report(b1=True, b2=True, b3=True)
    assert delivered_ids(full, beats) == ["b1", "b2", "b3"]
    assert undelivered(full, beats) == []
    print("  nothing to re-ask for")

    print("the swap failure: claimed everything, delivered one")
    thin = report(b1=True, b2=False, b3=False)
    assert [b.id for b in undelivered(thin, beats)] == ["b2", "b3"]
    assert [b.id for b in undelivered(thin, beats, load_bearing_only=True)] == ["b2"]
    assert reconcile(["b1", "b2", "b3"], thin, beats) == ["b2", "b3"]
    print(f"  undelivered {[b.id for b in undelivered(thin, beats)]}, "
          f"overclaimed {reconcile(['b1','b2','b3'], thin, beats)}")

    print("a missing verdict counts as undelivered, never as passed")
    partial = report(b1=True)
    assert [b.id for b in undelivered(partial, beats)] == ["b2", "b3"]
    print("  silence is not consent")

    print("verdicts for beats that were not assigned are ignored")
    noisy = DeliveryReport(
        verdicts=[
            BeatVerdict(beat_id="b1", delivered=True, note=""),
            BeatVerdict(beat_id="b99", delivered=True, note="hallucinated id"),
        ]
    )
    assert delivered_ids(noisy, beats) == ["b1"]
    print("  a hallucinated beat id cannot mark anything delivered")

    print("an honest writer produces no overclaim")
    assert reconcile(["b1"], thin, beats) == []
    print("  claimed only what it delivered -> nothing recorded")

    print("voting: the strict gate needs every ballot")
    split = merge_delivery([report(b1=True, b2=True, b3=True), thin], beats)
    got = {v.beat_id: v.delivered for v in split.verdicts}
    assert got == {"b1": True, "b2": False, "b3": False}, got
    print("  one dissenting ballot -> not delivered")

    print("voting: majority threshold for measurement")
    majority = merge_delivery(
        [report(b1=True, b2=True, b3=True), thin, report(b1=True, b2=True, b3=False)],
        beats,
        threshold=2,
    )
    got = {v.beat_id: v.delivered for v in majority.verdicts}
    assert got == {"b1": True, "b2": True, "b3": False}, got
    print("  2 of 3 carries a beat; 1 of 3 does not")

    print("voting: a ballot silent on a beat votes no")
    silent = merge_delivery([report(b1=True), report(b1=True, b2=True)], beats)
    got = {v.beat_id: v.delivered for v in silent.verdicts}
    assert got == {"b1": True, "b2": False, "b3": False}, got
    print("  missing verdicts cannot carry a beat")

    print()
    print("delivery check OK")
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Independent beat-delivery check.")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    raise SystemExit(_selftest())
