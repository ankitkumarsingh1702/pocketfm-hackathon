"""Genre packs — the free variables the skeleton deliberately leaves out.

A pack is data, not a prompt string. The skeleton says what happens; the pack
says what it feels like, sounds like, and is not allowed to do. Adding a sixth
genre is a JSON file, not a code change — which matters, because the first
question anyone asks a genre converter is whether it can do noir.

`taboo_moves` is the field that earns its keep. Positive instructions ("write
dread") produce competent prose in every genre; the prohibitions are what keep
horror from drifting into thriller.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import BaseModel, Field

GENRES_DIR = Path(__file__).parent / "genres"


class GenrePack(BaseModel):
    """Everything the transform stage is allowed to invent."""

    name: str
    premise: str = Field(description="The genre's core assumption about how its world works.")
    obligatory_beats: List[str] = Field(
        description="Moves a reader expects. Woven into the existing plot, never appended to it."
    )
    pacing_curve: str
    sensory_palette: List[str]
    pov_distance: str
    dialogue_register: str
    taboo_moves: List[str] = Field(description="Moves that would break the genre. Hard constraints.")

    def as_brief(self) -> str:
        """Render the pack for a prompt. Prohibitions last, so they land closest."""
        bullets = lambda items: "\n".join(f"  - {i}" for i in items)  # noqa: E731
        return (
            f"GENRE: {self.name}\n"
            f"PREMISE: {self.premise}\n"
            f"POV: {self.pov_distance}\n"
            f"DIALOGUE: {self.dialogue_register}\n"
            f"PACING: {self.pacing_curve}\n"
            f"SENSORY PALETTE — draw from these, do not use all of them:\n{bullets(self.sensory_palette)}\n"
            f"MOVES THE READER EXPECTS — weave into the plot you are given, never append:\n"
            f"{bullets(self.obligatory_beats)}\n"
            f"FORBIDDEN — these break the genre:\n{bullets(self.taboo_moves)}"
        )


def available_packs() -> List[str]:
    """Genre names with a JSON file on disk, sorted."""
    return sorted(p.stem for p in GENRES_DIR.glob("*.json"))


@lru_cache(maxsize=None)
def load_pack(name: str) -> GenrePack:
    """Load one pack by name, failing with the list of real options."""
    path = GENRES_DIR / f"{name}.json"
    if not path.exists():
        raise RuntimeError(
            f"No genre pack named {name!r}. Available: {', '.join(available_packs())}. "
            f"Add one by dropping a JSON file in {GENRES_DIR}/."
        )
    return GenrePack.model_validate(json.loads(path.read_text()))


if __name__ == "__main__":
    for genre in available_packs():
        print("=" * 68)
        print(load_pack(genre).as_brief())
