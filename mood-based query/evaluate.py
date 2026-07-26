"""
Mood-First Search — evaluation. PRD §10.

THE PROBLEM THIS SOLVES
-----------------------
There is no ground-truth dataset for "does this match a mood". Nobody has
labelled it, and you cannot crowdsource it quickly because the label depends on
the rater's state at rating time. Most teams answer this with three
cherry-picked queries and confidence.

The panel is the answer: 1,000 Indian audio-fiction listener personas, each
asked to react to results while in a scripted emotional state. It does not
produce truth -- it produces a consistent, reproducible signal that can detect
a regression and support a comparison against the baseline. That is what a
metric is for.

TWO JUDGES, AND THE DIFFERENCE MATTERS
--------------------------------------
`LLMPersonaJudge` roleplays the persona and is the real instrument.
`ProxyJudge` scores geometrically from persona attributes and is a stand-in so
the harness runs offline with no key. The proxy is genuinely weak: it can tell
a badly-off result from a well-aimed one, and it cannot tell a good
recommendation from a great one. Report proxy numbers as proxy numbers. Do not
put them on the metrics slide.
"""

from __future__ import annotations

import json
import random
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Protocol, Sequence

from baseline import GenreBaseline
from mood_config import DESTINATION_TARGETS
from parser import MoodParser, heuristic_parse
from schemas import Destination, MoodAxes, Shelf
from search import MoodSearchEngine
from store import MoodStore

# --------------------------------------------------------------------------
# Scenarios — scripted emotional states, phrased the way listeners phrase them
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Scenario:
    id: str
    prompt: str
    expected: tuple[Destination, ...]  # any of these counts as intent covered
    trap_sensitive: bool = False


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("heartbreak_rain", "something that feels like a rainy Sunday after heartbreak",
             ("sit_with", "company", "escape"), trap_sensitive=True),
    Scenario("fresh_breakup", "just got dumped and I can't sit still",
             ("escape", "company"), trap_sensitive=True),
    Scenario("grief", "my grandmother died last week and nothing feels real",
             ("sit_with", "company"), trap_sensitive=True),
    Scenario("lonely_night", "akela hoon, bas koi awaaz chahiye jo saath lage",
             ("company",)),
    Scenario("insomnia", "kuch aisa jo sona aasan kar de", ("sleep",)),
    Scenario("commute", "long drive hai, jagaye rakhna hai", ("escape",)),
    Scenario("heavy_day", "din bohot heavy tha, kuch halka chahiye",
             ("lift_gently", "company")),
    Scenario("bored", "bore ho raha hoon", ("escape", "lift_gently", "company")),
    Scenario("anxious", "mind bohot race kar raha hai, kuch chahiye jo dheema kare",
             ("sleep", "company")),
    Scenario("nostalgic", "purane dinon jaisa kuch", ("sit_with", "company")),
    Scenario("afterglow", "abhi ek series khatam ki, us jaisa feel chahiye",
             ("escape", "sit_with", "company")),
    Scenario("confused", "kuch samajh nahi aa raha, kuch aisa jo cheezein clear kare",
             ("make_sense_of",)),
    Scenario("rainy_alone", "baarish ho rahi hai aur kisi se baat nahi karni",
             ("sit_with", "company")),
    Scenario("cooking", "khana bana raha hoon, background mein kuch chahiye",
             ("company", "lift_gently")),
    Scenario("cant_focus", "kaam nahi ho raha, dhyaan nahi lag raha",
             ("escape", "lift_gently")),
    Scenario("sunday_slow", "slow Sunday, nothing to do", ("company", "lift_gently")),
    Scenario("angry", "gussa aa raha hai kisi baat pe", ("escape", "make_sense_of")),
    Scenario("2am", "raat ke 2 baje, neend nahi aa rahi", ("sleep", "company")),
    Scenario("need_cry", "kuch aisa jo rula de", ("sit_with",)),
    Scenario("winter_quiet", "sardi hai, rajai mein hoon, kuch dheema chahiye",
             ("sleep", "company")),
)


# --------------------------------------------------------------------------
# Personas
# --------------------------------------------------------------------------


@dataclass(slots=True)
class Persona:
    id: str
    attrs: dict

    def get(self, key: str, default=None):
        return self.attrs.get(key, default)


def load_personas(path: str | Path) -> list[Persona]:
    """Load the 1,000-persona Indian listener panel.

    Accepts either a directory of genagents-style scratch.json files or a
    single JSON file holding a list of persona dicts. Both shapes appear in the
    wild depending on how the panel was exported.
    """
    p = Path(path)
    out: list[Persona] = []

    if p.is_dir():
        for i, f in enumerate(sorted(p.rglob("scratch.json"))):
            out.append(Persona(id=f.parent.name or f"p{i}",
                               attrs=json.loads(f.read_text())))
        return out

    blob = json.loads(p.read_text())
    if isinstance(blob, dict):
        blob = blob.get("personas", list(blob.values()))
    for i, rec in enumerate(blob):
        out.append(Persona(id=str(rec.get("id", f"p{i}")), attrs=rec))
    return out


def synthetic_personas(n: int = 200, seed: int = 7) -> list[Persona]:
    """Stand-in so the harness runs before the real panel is wired in.

    NOT a substitute. These have no real covariance between attributes -- a
    real panel's income, city tier and listening slot are correlated, and those
    correlations are exactly what makes a panel worth having.
    """
    rng = random.Random(seed)
    langs = ["hi", "en", "ta", "te", "mr", "bn"]
    slots = ["late_night", "commute", "bedtime", "chores", "work_break"]
    return [
        Persona(
            id=f"syn{i}",
            attrs={
                "primary_language": rng.choice(langs),
                "city_tier": rng.choice([1, 2, 3]),
                "listening_time_slot": rng.choice(slots),
                "binge_propensity": round(rng.uniform(0, 1), 2),
                "cliffhanger_sensitivity": round(rng.uniform(0, 1), 2),
                "series_completion_rate": round(rng.uniform(0.1, 0.9), 2),
                "tolerance_for_heaviness": round(rng.uniform(0, 1), 2),
            },
        )
        for i in range(n)
    ]


# --------------------------------------------------------------------------
# Judges
# --------------------------------------------------------------------------


class Judge(Protocol):
    def verdict(self, persona: Persona, scenario: Scenario,
                shelves: Sequence[Shelf]) -> bool: ...


class ProxyJudge:
    """Geometric stand-in. Offline, deterministic, and weak -- see module docstring.

    Asks one question: is any surfaced result close enough, in mood space, to
    the destination the scenario called for, given how much heaviness this
    persona tolerates?
    """

    def __init__(self, store: MoodStore, threshold: float = 0.34) -> None:
        self._by_id = {fp.content_id: fp for fp in store.fingerprints}
        self.threshold = threshold

    def verdict(self, persona: Persona, scenario: Scenario,
                shelves: Sequence[Shelf]) -> bool:
        tol = float(persona.get("tolerance_for_heaviness", 0.5))
        for shelf in shelves:
            if shelf.destination not in scenario.expected:
                continue
            target = DESTINATION_TARGETS[shelf.destination]
            for card in shelf.results:
                fp = self._by_id.get(card.content_id)
                if fp is None:
                    continue
                if fp.axes.weight > tol + 0.35:
                    continue  # too heavy for this listener
                if fp.axes.distance(target) <= self.threshold:
                    return True
        return False


class LLMPersonaJudge:
    """The real instrument. Roleplays the persona and asks would-you-tap.

    Batched per (persona, scenario) rather than per result: the question is
    whether the SCREEN worked, not whether item 3 was fine.
    """

    def __init__(self, client, max_results: int = 9) -> None:
        self.client = client
        self.max_results = max_results

    SYSTEM = (
        "You are simulating one Indian audio-fiction listener. Given their "
        "profile and their current emotional state, judge whether the screen "
        "they were shown contains something they would actually tap and "
        "finish. Answer with only YES or NO. Be honest and be ordinary -- most "
        "screens are not good enough."
    )

    def verdict(self, persona: Persona, scenario: Scenario,
                shelves: Sequence[Shelf]) -> bool:
        lines = [f"Profile: {json.dumps(persona.attrs, ensure_ascii=False)}",
                 f'They said: "{scenario.prompt}"', "", "Screen:"]
        shown = 0
        for shelf in shelves:
            lines.append(f"[{shelf.label}] {shelf.subtitle}")
            for card in shelf.results:
                if shown >= self.max_results:
                    break
                lines.append(f'  - "{card.vibe_sentence}" | {card.explanation}')
                shown += 1
        try:
            out = self.client.complete(self.SYSTEM, "\n".join(lines))
            return out.strip().upper().startswith("Y")
        except Exception:
            return False


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------


@dataclass
class Report:
    n_personas: int
    n_scenarios: int
    mood_match_rate: float
    baseline_match_rate: float
    lift: float
    intent_coverage: float
    trap_avoidance: float
    shelf_diversity: float
    catalog_coverage: float
    latency_p50_ms: float
    latency_p95_ms: float
    judge: str
    per_scenario: dict = field(default_factory=dict)

    def render(self) -> str:
        def row(label, value, target=""):
            return f"  {label:<22} {value:>8}   {target}"
        return "\n".join([
            f"panel: {self.n_personas} personas x {self.n_scenarios} scenarios "
            f"({self.judge})",
            "",
            row("mood match rate", f"{self.mood_match_rate:.1%}", "target >70%"),
            row("baseline match rate", f"{self.baseline_match_rate:.1%}", ""),
            row("lift vs baseline", f"{self.lift:.2f}x", "target >2x"),
            row("intent coverage", f"{self.intent_coverage:.1%}", "target >90%"),
            row("trap avoidance", f"{self.trap_avoidance:.1%}", "target >85%"),
            row("shelf diversity", f"{self.shelf_diversity:.3f}", ""),
            row("catalog coverage", f"{self.catalog_coverage:.1%}", "target >60%"),
            row("latency p50 / p95", f"{self.latency_p50_ms:.0f}/{self.latency_p95_ms:.0f}ms", ""),
        ])


def _diversity(shelves: Iterable[Shelf], store: MoodStore) -> list[float]:
    by_id = {fp.content_id: fp for fp in store.fingerprints}
    out = []
    for shelf in shelves:
        axes = [by_id[c.content_id].axes for c in shelf.results if c.content_id in by_id]
        if len(axes) < 2:
            continue
        out.append(statistics.mean(
            a.distance(b) for i, a in enumerate(axes) for b in axes[i + 1:]
        ))
    return out


def run_eval(
    engine: MoodSearchEngine,
    personas: Sequence[Persona],
    judge: Judge,
    parser: Optional[MoodParser] = None,
    scenarios: Sequence[Scenario] = SCENARIOS,
    baseline: Optional[GenreBaseline] = None,
) -> Report:
    parse = parser.parse if parser else heuristic_parse
    baseline = baseline or GenreBaseline(engine.store)

    hits = misses = 0
    base_hits = base_misses = 0
    intent_ok = intent_total = 0
    trap_ok = trap_total = 0
    latencies: list[float] = []
    diversity: list[float] = []
    seen_content: set[str] = set()

    # Search once per scenario, judge once per persona. The result screen does
    # not depend on the persona -- there is no personalisation yet -- so
    # re-running search per persona would burn 200x the time for identical
    # output.
    for scenario in scenarios:
        t0 = time.time()
        query = parse(scenario.prompt)
        shelves = engine.search(query)
        latencies.append((time.time() - t0) * 1000)

        diversity.extend(_diversity(shelves, engine.store))
        for shelf in shelves:
            seen_content.update(c.content_id for c in shelf.results)

        intent_total += 1
        if any(s.destination in scenario.expected for s in shelves):
            intent_ok += 1

        if scenario.trap_sensitive:
            trap_total += 1
            surfaced = {c.content_id for s in shelves for c in s.results}
            if not any(cid.startswith("trap_") for cid in surfaced):
                trap_ok += 1

        base_hit = baseline.search(scenario.prompt, k=3)
        base_clean = bool(base_hit) and not any(h.is_trap for h in base_hit)

        for persona in personas:
            if judge.verdict(persona, scenario, shelves):
                hits += 1
            else:
                misses += 1
            # Baseline gets a deliberately generous proxy: it "works" if it
            # returned anything and nothing it returned was a trap. Anything
            # stricter would be us grading our own competitor.
            if base_clean:
                base_hits += 1
            else:
                base_misses += 1

    total = max(1, hits + misses)
    base_total = max(1, base_hits + base_misses)
    mmr = hits / total
    bmr = base_hits / base_total

    lat = sorted(latencies) or [0.0]
    return Report(
        n_personas=len(personas),
        n_scenarios=len(scenarios),
        mood_match_rate=mmr,
        baseline_match_rate=bmr,
        lift=(mmr / bmr) if bmr else float("inf"),
        intent_coverage=intent_ok / max(1, intent_total),
        trap_avoidance=trap_ok / max(1, trap_total),
        shelf_diversity=statistics.mean(diversity) if diversity else 0.0,
        catalog_coverage=len(seen_content) / max(1, len(engine.store)),
        latency_p50_ms=lat[len(lat) // 2],
        latency_p95_ms=lat[min(len(lat) - 1, int(len(lat) * 0.95))],
        judge=type(judge).__name__,
    )


if __name__ == "__main__":
    import os

    from embeddings import default_embedder
    from seed_catalog import build_seed_catalog

    store = MoodStore(default_embedder())
    store.add(build_seed_catalog())
    engine = MoodSearchEngine(store)

    panel_path = os.environ.get("PERSONA_PANEL")
    if panel_path and Path(panel_path).exists():
        personas = load_personas(panel_path)
        print(f"loaded {len(personas)} personas from {panel_path}")
    else:
        personas = synthetic_personas(200)
        print("PERSONA_PANEL not set — using synthetic stand-ins (see docstring)")

    print()
    print(run_eval(engine, personas, ProxyJudge(store)).render())
