"""
Mood-First Search — embeddings.

WHY WE EMBED `vibe_sentence` AND NOT THE SYNOPSIS
--------------------------------------------------
The PRD's whole premise is that embedding plot text fails: synopses describe
events, queries describe felt experience, and the two live in different
semantic neighbourhoods. That argument is about SYNOPSES.

`vibe_sentence` is written by the fingerprinter in experiential language --
the same register the listener types in. So query<->vibe cosine is a
legitimate signal, and it is the ONLY place we let embeddings vote. If someone
later points the embedder at `synopsis`, the retrieval quality collapses and
the failure is silent. Don't.

Embedders are swappable behind `Embedder`. HashingEmbedder is deterministic,
dependency-free and offline -- it is the CI/test default and the demo-day
fallback if a provider is down. It is genuinely weak on synonymy; use a real
model in the demo path.
"""

from __future__ import annotations

import hashlib
import re
from typing import Protocol, Sequence

import numpy as np

DIM = 256


class Embedder(Protocol):
    dim: int

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        """(n_texts, dim) float32, L2-normalised."""
        ...


def _l2(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (mat / norms).astype(np.float32)


class HashingEmbedder:
    """Character-trigram + word hashing into a fixed space.

    Deterministic across processes and machines -- no model download, no
    network, byte-identical results in CI. Captures lexical overlap only.
    """

    def __init__(self, dim: int = DIM) -> None:
        self.dim = dim

    @staticmethod
    def _tokens(text: str) -> list[str]:
        text = text.lower()
        words = re.findall(r"[a-z\u0900-\u097F]+", text)
        grams = [w[i:i + 3] for w in words for i in range(max(1, len(w) - 2))]
        return words + grams

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for tok in self._tokens(text):
                h = hashlib.blake2b(tok.encode(), digest_size=8).digest()
                idx = int.from_bytes(h[:4], "little") % self.dim
                sign = 1.0 if h[4] & 1 else -1.0
                out[row, idx] += sign
        return _l2(out)


class SentenceTransformerEmbedder:
    """Real semantic embeddings. Use this for the demo.

    bge-small-en-v1.5 is 33M params, CPU-fine, and handles the Hinglish we get
    in queries better than MiniLM in our spot checks.
    """

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        from sentence_transformers import SentenceTransformer  # lazy

        self._model = SentenceTransformer(model_name)
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        vecs = self._model.encode(
            list(texts), convert_to_numpy=True, normalize_embeddings=True
        )
        return vecs.astype(np.float32)


class CachedEmbedder:
    """Memoises by exact string.

    Matters more than it looks: the same ~640 vibe sentences get re-encoded on
    every reindex, and during the demo the same query text is hit repeatedly by
    slider refinement.
    """

    def __init__(self, inner: Embedder) -> None:
        self._inner = inner
        self.dim = inner.dim
        self._cache: dict[str, np.ndarray] = {}

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        missing = [t for t in texts if t not in self._cache]
        if missing:
            fresh = self._inner.encode(missing)
            for text, vec in zip(missing, fresh):
                self._cache[text] = vec
        return np.vstack([self._cache[t] for t in texts]).astype(np.float32)


def default_embedder() -> Embedder:
    """Real model if present, deterministic fallback otherwise.

    Never raises. A missing model degrades retrieval quality; it must not take
    the demo down.
    """
    try:
        return CachedEmbedder(SentenceTransformerEmbedder())
    except Exception:
        return CachedEmbedder(HashingEmbedder())
