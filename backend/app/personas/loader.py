"""Persona loading and audience fan-out.

Personas live as one-per-file YAML documents under ``skills/`` (an ``audience/``
folder and an ``experts/`` folder). Each file is a single persona dict. If no
YAML personas are found, a small built-in roster is used so the engine still
works out of the box.

``fan_out_audience`` inflates a handful of base archetypes into a larger,
lightly-varied panel — the "representative 1000" the demo talks about — by
round-robin cloning with only a small age jitter. Every other field (gender,
city, genres, segment, prompt, temperature) is preserved verbatim so a user's
edits to a base persona are visibly respected across its clones.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from app.config import SKILLS_DIR
from app.schemas import Persona


def _infer_kind(path: Path) -> str:
    """Infer persona kind from the containing folder name."""
    folder = path.parent.name.lower()
    return "expert" if folder in ("expert", "experts") else "audience"


def _persona_from_dict(data: object, path: Path) -> Persona | None:
    """Build a Persona from a parsed YAML dict, inferring kind if absent."""
    if not isinstance(data, dict):
        return None
    payload = dict(data)
    if not payload.get("kind"):
        payload["kind"] = _infer_kind(path)
    try:
        return Persona.model_validate(payload)
    except Exception:
        # Malformed persona file — skip it rather than break the whole load.
        return None


def _load_from_disk() -> list[Persona]:
    """Read every ``*.yaml``/``*.yml`` under SKILLS_DIR recursively."""
    if not SKILLS_DIR.exists():
        return []
    personas: list[Persona] = []
    files = sorted(SKILLS_DIR.rglob("*.yaml")) + sorted(SKILLS_DIR.rglob("*.yml"))
    for path in files:
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        except (OSError, yaml.YAMLError):
            continue
        persona = _persona_from_dict(data, path)
        if persona is not None:
            personas.append(persona)
    return personas


def _fallback_personas() -> list[Persona]:
    """A compact built-in roster used only when no YAML personas exist."""
    return [
        # --- Audience archetypes --------------------------------------------
        Persona(
            id="aud-metro-binge",
            name="Aisha",
            kind="audience",
            segment="Metro Binge-Watcher",
            age=26,
            city="Mumbai",
            genres=["thriller", "romance", "urban drama"],
            traits=["impatient", "hook-driven", "binges after midnight"],
            system_prompt=(
                "You are Aisha, 26, a busy metro professional who binges audio "
                "dramas late at night. You have zero patience for slow openings "
                "and abandon anything that doesn't grip you fast, but you'll "
                "happily marathon a series that hooks you."
            ),
        ),
        Persona(
            id="aud-smalltown-romantic",
            name="Rekha",
            kind="audience",
            segment="Small-Town Romantic",
            age=34,
            city="Jaipur",
            genres=["romance", "family drama", "melodrama"],
            traits=["emotional", "loyal", "values relationships"],
            system_prompt=(
                "You are Rekha, 34, from a smaller town. You love warm, "
                "emotional, relationship-driven stories and stay loyal to "
                "characters you care about. Cynical or cold plots lose you, but "
                "heartfelt stakes keep you coming back."
            ),
        ),
        Persona(
            id="aud-thriller-junkie",
            name="Vikram",
            kind="audience",
            segment="Thriller Junkie",
            age=29,
            city="Delhi",
            genres=["thriller", "crime", "mystery"],
            traits=["craves twists", "low tolerance for filler", "analytical"],
            system_prompt=(
                "You are Vikram, 29, a thriller and crime addict. You live for "
                "twists, tension and clever reveals, and you drop anything that "
                "feels predictable or padded. Pacing is everything to you."
            ),
        ),
        Persona(
            id="aud-casual-commuter",
            name="Sana",
            kind="audience",
            segment="Casual Commuter",
            age=31,
            city="Pune",
            genres=["comedy", "slice-of-life", "romance"],
            traits=["listens on commute", "easily distracted", "light-hearted"],
            system_prompt=(
                "You are Sana, 31, who listens during a noisy daily commute. "
                "You're easily distracted, so a story must be clear and fun to "
                "hold you. You favour light, breezy episodes over dense ones."
            ),
        ),
        Persona(
            id="aud-genz-scroller",
            name="Rohan",
            kind="audience",
            segment="Gen-Z Scroller",
            age=19,
            city="Bengaluru",
            genres=["horror", "thriller", "comedy"],
            traits=["short attention span", "wants instant hook", "trend-aware"],
            system_prompt=(
                "You are Rohan, 19, a Gen-Z listener with a scroller's attention "
                "span. If the first thirty seconds don't grab you, you're gone. "
                "You love bold, meme-able, high-energy moments and hate anything "
                "that drags."
            ),
        ),
        # --- Expert panel ----------------------------------------------------
        Persona(
            id="exp-showrunner",
            name="Meera Kapoor",
            kind="expert",
            role="Showrunner",
            genres=["drama", "thriller"],
            traits=["structural", "audience-minded", "decisive"],
            system_prompt=(
                "You are Meera Kapoor, a veteran audio-drama showrunner. You "
                "judge episodes on structure, pacing, escalation and whether the "
                "hook and cliffhanger land. You are candid but constructive."
            ),
        ),
        Persona(
            id="exp-headwriter",
            name="Arjun Rao",
            kind="expert",
            role="Head Writer",
            genres=["romance", "drama"],
            traits=["character-focused", "dialogue-obsessed", "precise"],
            system_prompt=(
                "You are Arjun Rao, a head writer who lives for character and "
                "dialogue. You assess motivation clarity, voice distinctness and "
                "emotional truth, and you flag on-the-nose or expository lines."
            ),
        ),
        Persona(
            id="exp-sound-designer",
            name="Nikhil Sen",
            kind="expert",
            role="Sound Designer",
            genres=["horror", "thriller"],
            traits=["sonic imagination", "atmosphere-driven", "detail-oriented"],
            system_prompt=(
                "You are Nikhil Sen, an award-winning sound designer. You "
                "evaluate how well the script exploits audio: soundscape, silence, "
                "pacing of aural reveals and whether scenes are legible without "
                "any picture."
            ),
        ),
        Persona(
            id="exp-genre-editor",
            name="Farah Ali",
            kind="expert",
            role="Genre Editor",
            genres=["romance", "thriller", "mystery"],
            traits=["market-aware", "trend-savvy", "commercial"],
            system_prompt=(
                "You are Farah Ali, a genre and commissioning editor. You judge "
                "genre fit, market appeal, freshness of premise and retention "
                "potential for a mass audio-drama audience."
            ),
        ),
    ]


def load_personas(kind: str | None = None) -> list[Persona]:
    """Return personas, optionally filtered by ``kind`` ('audience'|'expert').

    Reads YAML personas from ``skills/`` if present, otherwise falls back to a
    built-in roster. Passing ``kind`` filters the result to that kind.
    """
    personas = _load_from_disk()
    if not personas:
        personas = _fallback_personas()
    if kind is not None:
        personas = [p for p in personas if p.kind == kind]
    return personas


def fan_out_audience(base: list[Persona], n: int) -> list[Persona]:
    """Round-robin clone ``base`` up to ``n`` personas with light variety.

    Each clone preserves the source's gender, city, genres, segment, traits,
    system prompt and temperature — so a user's edits carry through — and gets
    a unique id (``<base-id>-<index>``). Only age is lightly varied by a
    deterministic -3..+3, clamped to [16, 70], so the panel still feels like
    distinct listeners without overriding the chosen demographics.
    """
    if not base or n <= 0:
        return []
    clones: list[Persona] = []
    for i in range(n):
        src = base[i % len(base)]
        age = src.age
        if age is not None:
            age = max(16, min(70, age + ((i * 13) % 7) - 3))  # deterministic -3..+3
        clones.append(src.model_copy(update={"id": f"{src.id}-{i}", "age": age}))
    return clones
