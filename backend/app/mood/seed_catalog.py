"""
Mood-First Search — seed catalog.

TEST FIXTURE, NOT THE CATALOG. Tier B synthetic arcs, deterministic under a
fixed seed so retrieval tests are reproducible. Ritik's real fingerprints
replace this wholesale at H8; nothing downstream knows the difference because
everything speaks MoodFingerprint.

The fixture deliberately includes TRAPS: arcs whose vibe sentence and sensory
tags overlap heavily with the hero query but which are emotionally wrong for
it. Without traps a retrieval test only proves we can find things, which is the
easy half. The trap arcs are what the contraindication layer exists for, and
`test_retrieval` asserts they never surface.
"""

from __future__ import annotations

import random

from app.mood.schemas import MoodAxes, MoodFingerprint

SEED = 20260725

# The whole point of the fixture. Every one of these overlaps hard with
# "rainy Sunday after heartbreak" on words and tags, and every one would make a
# freshly heartbroken listener worse.
TRAPS: list[dict] = [
    dict(
        series_title="Barsaat Ke Baad",
        arc_label="the parting arc",
        vibe_sentence="Monsoon-soaked and aching, two people come apart in the rain.",
        sensory_tags=["rain", "monsoon", "night"],
        good_for=["a good cry"],
        contraindicated_for=["someone going through a breakup", "fresh heartbreak"],
        axes=MoodAxes(valence=-0.8, arousal=0.4, tension=0.6, warmth=0.3,
                      pace=0.4, catharsis=0.9, hope=0.1, companionship=0.3, weight=0.9),
    ),
    dict(
        series_title="Aakhri Chitthi",
        arc_label="the letters arc",
        vibe_sentence="Rain on a window, a Sunday, and a love that does not survive it.",
        sensory_tags=["rain", "small-room", "night"],
        good_for=["heavy nights"],
        contraindicated_for=["a fresh breakup", "raw grief"],
        axes=MoodAxes(valence=-0.75, arousal=0.3, tension=0.5, warmth=0.35,
                      pace=0.3, catharsis=0.85, hope=0.15, companionship=0.35, weight=0.85),
    ),
    dict(
        series_title="Saawan Bemausam",
        arc_label="the flood arc",
        vibe_sentence="A rainy Sunday that takes everything, slowly and then all at once.",
        sensory_tags=["rain", "monsoon", "small-room"],
        good_for=["catharsis"],
        contraindicated_for=["someone who wants cheering up", "heartbreak"],
        axes=MoodAxes(valence=-0.85, arousal=0.5, tension=0.75, warmth=0.2,
                      pace=0.5, catharsis=0.8, hope=0.05, companionship=0.2, weight=0.95),
    ),
]

# Non-trap templates, one per destination neighbourhood.
TEMPLATES: list[dict] = [
    dict(
        kind="sit_with",
        titles=["Dhoop Ka Tukda", "Adhoora Raag", "Chhoti Si Baat", "Sheher Ki Chhat"],
        vibes=[
            "Quiet, unhurried, and it lets you be sad without commentary.",
            "Somebody speaking softly about a loss that isn't yours.",
            "Slow and rain-coloured, and it never asks you to move on.",
        ],
        tags=["rain", "night", "small-room"],
        good_for=["crying it out", "sitting with it", "alone at night"],
        contra=["someone who wants cheering up"],
        axes=dict(valence=(-0.7, -0.3), arousal=(0.1, 0.35), tension=(0.05, 0.35),
                  warmth=(0.55, 0.85), pace=(0.1, 0.35), catharsis=(0.6, 0.95),
                  hope=(0.3, 0.55), companionship=(0.35, 0.6), weight=(0.6, 0.9)),
    ),
    dict(
        kind="company",
        titles=["Chai Aur Do Baatein", "Raat Ke Do Baje", "Padosi", "Khidki"],
        vibes=[
            "Mostly two people talking about nothing, warmly, for hours.",
            "A voice close to the mic, telling you about their day.",
            "Small, kind, and nothing bad happens in it.",
        ],
        tags=["small-room", "night", "winter-quilt"],
        good_for=["company", "background comfort", "cosy nights"],
        contra=["someone who wants a plot"],
        axes=dict(valence=(0.0, 0.4), arousal=(0.15, 0.4), tension=(0.02, 0.25),
                  warmth=(0.75, 0.98), pace=(0.15, 0.4), catharsis=(0.1, 0.4),
                  hope=(0.5, 0.8), companionship=(0.75, 0.98), weight=(0.1, 0.35)),
    ),
    dict(
        kind="escape",
        titles=["Kaala Samandar", "Teesri Duniya", "Highway 47", "Andheri Suranga"],
        vibes=[
            "Fast, strange, and it grabs you inside two minutes.",
            "A world with its own weather and its own rules.",
            "Propulsive enough that you forget where you are.",
        ],
        tags=["open-road", "crowd", "night"],
        good_for=["binge", "long commute", "immersive escape", "drive"],
        contra=["winding down", "falling asleep"],
        axes=dict(valence=(-0.1, 0.5), arousal=(0.6, 0.9), tension=(0.45, 0.8),
                  warmth=(0.2, 0.5), pace=(0.65, 0.95), catharsis=(0.1, 0.4),
                  hope=(0.4, 0.75), companionship=(0.1, 0.4), weight=(0.3, 0.6)),
    ),
    dict(
        kind="lift_gently",
        titles=["Halki Dhoop", "Naya Mausam", "Pehli Baarish", "Rasta Khula Hai"],
        vibes=[
            "Warm without being loud about it, and it ends better than it starts.",
            "Light on its feet, and it doesn't ask much of you.",
            "Small good things happening to people who deserve them.",
        ],
        tags=["morning", "open-road", "summer"],
        good_for=["cheer up", "light listening", "a lift"],
        contra=["raw grief", "someone who wants to sit in it"],
        axes=dict(valence=(0.25, 0.65), arousal=(0.25, 0.5), tension=(0.05, 0.3),
                  warmth=(0.65, 0.9), pace=(0.25, 0.5), catharsis=(0.15, 0.45),
                  hope=(0.65, 0.95), companionship=(0.4, 0.7), weight=(0.15, 0.4)),
    ),
    dict(
        kind="sleep",
        titles=["Neend Se Pehle", "Dheemi Aawaz", "Raat Ki Kahani", "Chandni Raat"],
        vibes=[
            "Dark, slow, and it never raises its voice.",
            "Built to be half-heard on the way under.",
            "Nothing urgent, told very quietly.",
        ],
        tags=["night", "winter-quilt", "small-room"],
        good_for=["sleep", "bedtime", "wind down"],
        contra=["a long drive", "staying awake"],
        axes=dict(valence=(0.0, 0.35), arousal=(0.02, 0.18), tension=(0.0, 0.15),
                  warmth=(0.7, 0.95), pace=(0.03, 0.2), catharsis=(0.05, 0.25),
                  hope=(0.45, 0.75), companionship=(0.55, 0.85), weight=(0.1, 0.3)),
    ),
    dict(
        kind="make_sense_of",
        titles=["Uska Hissa", "Jo Bacha Reh Gaya", "Teen Saal Baad", "Wapsi"],
        vibes=[
            "Someone else thought carefully about the thing you can't name.",
            "It puts a shape around a mess, patiently.",
            "Reflective, clear-eyed, and it lands somewhere.",
        ],
        tags=["evening", "small-room", "rain"],
        good_for=["thinking", "processing", "reflect"],
        contra=["low attention", "driving"],
        axes=dict(valence=(-0.2, 0.25), arousal=(0.3, 0.5), tension=(0.2, 0.45),
                  warmth=(0.45, 0.7), pace=(0.3, 0.5), catharsis=(0.4, 0.7),
                  hope=(0.45, 0.75), companionship=(0.45, 0.75), weight=(0.45, 0.75)),
    ),
]


def _axes_from(rng: random.Random, spec: dict) -> MoodAxes:
    return MoodAxes(**{k: round(rng.uniform(*v), 3) for k, v in spec.items()})


def build_seed_catalog(
    n_series: int = 48, arcs_per_series: tuple[int, int] = (2, 4), seed: int = SEED
) -> list[MoodFingerprint]:
    rng = random.Random(seed)
    out: list[MoodFingerprint] = []

    for i, trap in enumerate(TRAPS):
        out.append(
            MoodFingerprint(
                content_id=f"trap_{i}", series_id=f"trap_s{i}",
                series_title=trap["series_title"], arc_label=trap["arc_label"],
                entry_episode=rng.randint(8, 40),
                episode_span=(1, 120),
                axes=trap["axes"], sensory_tags=trap["sensory_tags"],
                vibe_sentence=trap["vibe_sentence"], good_for=trap["good_for"],
                contraindicated_for=trap["contraindicated_for"],
                duration_min=rng.randint(18, 30), audio_verified=False,
                axes_variance=round(rng.uniform(0.05, 0.3), 3), confidence=0.8,
            )
        )

    for s in range(n_series):
        tpl = TEMPLATES[s % len(TEMPLATES)]
        title = f"{rng.choice(tpl['titles'])} {rng.randint(1, 99)}"
        n_arcs = rng.randint(*arcs_per_series)
        span_hi = rng.randint(60, 220)
        cursor = 1

        # A series is not one mood. It swings -- that is the entire reason we
        # index arcs instead of series, and a fixture where every arc of a show
        # sits on the same point contradicts the premise it is meant to test.
        # Without this, retrieval has no reason ever to prefer a deep arc and
        # every entry point degenerates to "start from the beginning".
        drift_axes = rng.sample(
            ["valence", "arousal", "tension", "warmth", "pace", "catharsis", "hope", "weight"],
            k=3,
        )
        direction = {ax: rng.choice([-1.0, 1.0]) for ax in drift_axes}

        for a in range(n_arcs):
            length = max(6, span_hi // (n_arcs + 1))
            entry = cursor
            cursor += length + rng.randint(0, 6)
            axes = _axes_from(rng, tpl["axes"])
            if a:
                step = rng.uniform(0.14, 0.26) * a
                axes = axes.nudge({ax: direction[ax] * step for ax in drift_axes})
            out.append(
                MoodFingerprint(
                    content_id=f"s{s}_a{a}", series_id=f"s{s}", series_title=title,
                    arc_label=rng.choice([
                        "the monsoon arc", "the opening arc", "the quiet arc",
                        "the turn", "the last stretch", "the winter arc",
                    ]),
                    entry_episode=min(entry, span_hi),
                    episode_span=(1, span_hi),
                    axes=axes,
                    sensory_tags=rng.sample(tpl["tags"], k=rng.randint(1, len(tpl["tags"]))),
                    vibe_sentence=rng.choice(tpl["vibes"]),
                    good_for=rng.sample(tpl["good_for"], k=min(2, len(tpl["good_for"]))),
                    contraindicated_for=list(tpl["contra"]),
                    duration_min=rng.randint(15, 35),
                    language="en",
                    # ~8% Tier A, matching the real 40-of-640 split
                    audio_verified=(rng.random() < 0.08),
                    axes_variance=round(rng.uniform(0.03, 0.35), 3),
                    confidence=round(rng.uniform(0.6, 0.95), 2),
                )
            )
    return out
