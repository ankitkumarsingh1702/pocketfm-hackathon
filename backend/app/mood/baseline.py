"""
Mood-First Search — the baseline we are arguing against. PRD §14, beat 7.

This is a faithful, non-strawman implementation of how audio discovery works
today: lexical match over titles, tags and descriptions, ranked by term
overlap, with an optional genre filter. No mood axes, no destination, no
contraindications.

It is deliberately NOT crippled. Making the baseline bad on purpose would be
the easiest way to lose an argument you should win on merit -- a judge who
suspects the comparison is rigged discounts the whole demo. So it uses the same
catalog, the same text, and a standard TF-style ranking, and it is allowed to
do its best.

Its best is the point. On "rainy Sunday after heartbreak" it ranks the trap
arcs first, because they are the strongest lexical match in the catalog: they
are literally about rain, Sundays and heartbreak. That is the failure mode, and
it is not a bug in the baseline -- it is what topical matching does to an
emotional query.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Optional

from app.mood.store import MoodStore

_STOP = frozenset("""
a an the and or of to in on at for with without from by is are was were be been
i me my mine you your it its this that these those something anything some any
like feels feel felt want wanted need needed after before something's
""".split())


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z\u0900-\u097F]+", text.lower())
            if t not in _STOP and len(t) > 1]


@dataclass(slots=True)
class BaselineHit:
    content_id: str
    series_title: str
    entry_episode: int
    snippet: str
    score: float
    is_trap: bool


class GenreBaseline:
    """Classic lexical search over the same catalog. Built once, reused."""

    def __init__(self, store: MoodStore) -> None:
        self.store = store
        self._docs: list[list[str]] = []
        self._df: Counter[str] = Counter()

        for fp in store.fingerprints:
            doc = tokenize(
                f"{fp.series_title} {fp.arc_label} {fp.vibe_sentence} "
                f"{' '.join(fp.sensory_tags)} {' '.join(fp.good_for)}"
            )
            self._docs.append(doc)
            self._df.update(set(doc))

        self._n = max(1, len(self._docs))

    def _idf(self, term: str) -> float:
        return math.log(1 + self._n / (1 + self._df.get(term, 0)))

    def search(self, text: str, k: int = 3, genre: Optional[str] = None) -> list[BaselineHit]:
        terms = tokenize(text)
        if not terms:
            return []

        scored: list[tuple[float, int]] = []
        for row, doc in enumerate(self._docs):
            if not doc:
                continue
            if genre and genre.lower() not in " ".join(doc):
                continue
            counts = Counter(doc)
            score = sum(
                (1 + math.log(counts[t])) * self._idf(t)
                for t in set(terms) if t in counts
            )
            if score > 0:
                scored.append((score / math.sqrt(len(doc)), row))

        scored.sort(reverse=True)
        top = scored[:k]
        if not top:
            return []

        norm = top[0][0] or 1.0
        return [
            BaselineHit(
                content_id=self.store.fingerprints[row].content_id,
                series_title=self.store.fingerprints[row].series_title,
                entry_episode=self.store.fingerprints[row].entry_episode,
                snippet=self.store.fingerprints[row].vibe_sentence,
                score=round(score / norm, 3),
                is_trap=self.store.fingerprints[row].content_id.startswith("trap_"),
            )
            for score, row in top
        ]
