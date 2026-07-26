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
import os
import re
from typing import Protocol, Sequence

import numpy as np

DIM = 256

# Vertex text-embedding model. Region-pinned like every other Vertex call, so it
# reuses `settings.vertex_location` rather than inventing a second region knob.
VERTEX_EMBED_MODEL = os.environ.get("MOOD_EMBED_MODEL", "text-embedding-005")
# Vertex caps instances per embed request; stay well under it.
VERTEX_BATCH = 100


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


class VertexEmbedder:
    """Real semantic embeddings on Vertex AI via ADC. The production path.

    WHY THIS MATTERS MORE THAN IT LOOKS
    -----------------------------------
    The 0.30 semantic weight in `retrieval.ScoringWeights` is the term that is
    supposed to bridge the gap the whole PRD is built on: the listener types
    felt experience, and `vibe_sentence` is written in felt experience, so the
    cosine between them carries real signal. With `HashingEmbedder` behind it
    that term is character-trigram overlap -- it scores "rainy" against "rain"
    and nothing against "monsoon-soaked". The premise only actually holds with a
    model that knows synonymy, so this is the embedder the demo should run on.

    Uses `google-genai`, already a project dependency, with the same ADC auth and
    the same `settings` as every other Vertex call in the studio. No new
    credentials, no new region knob, no new dependency.

    `SEMANTIC_SIMILARITY` is the right task type here rather than the asymmetric
    RETRIEVAL_QUERY/RETRIEVAL_DOCUMENT pair: both sides of this comparison are
    short affective descriptions in the same register, which is symmetric by
    design. Asymmetric task types assume a short query against a long document,
    which is not the shape of this problem.
    """

    def __init__(
        self,
        model: str = VERTEX_EMBED_MODEL,
        project: str | None = None,
        location: str | None = None,
    ) -> None:
        from google import genai

        from app.config import settings

        self._client = genai.Client(
            vertexai=True,
            project=project or settings.google_cloud_project,
            location=location or settings.vertex_location,
        )
        self._model = model
        self.failures = 0

        # Probe once, at construction, so an unavailable model degrades to the
        # fallback embedder HERE rather than halfway through indexing -- a
        # half-embedded store is far worse than a weaker one.
        probe = self._embed(["ping"])
        self.dim = int(probe.shape[1])

    def _embed(self, texts: Sequence[str]) -> np.ndarray:
        from google.genai import types

        out: list[list[float]] = []
        for i in range(0, len(texts), VERTEX_BATCH):
            chunk = list(texts[i:i + VERTEX_BATCH])
            resp = self._client.models.embed_content(
                model=self._model,
                contents=chunk,
                config=types.EmbedContentConfig(task_type="SEMANTIC_SIMILARITY"),
            )
            out.extend(list(e.values) for e in resp.embeddings)
        return _l2(np.asarray(out, dtype=np.float32))

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        try:
            return self._embed(texts)
        except Exception:
            # A transient embedding failure must not 500 a search. Zero vectors
            # make the semantic term contribute exactly nothing for this call,
            # so axes and tags still rank -- degraded, not down. Counted so
            # /health can report it instead of failing silently.
            self.failures += 1
            return np.zeros((len(texts), self.dim), dtype=np.float32)


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

    @property
    def inner(self) -> Embedder:
        """The wrapped embedder. Exposed so /health can report which model is
        actually live -- 'CachedEmbedder' tells an operator nothing, and the
        difference between real semantics and lexical hashing is the difference
        between the premise holding and not."""
        return self._inner

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        missing = [t for t in texts if t not in self._cache]
        if missing:
            fresh = self._inner.encode(missing)
            for text, vec in zip(missing, fresh):
                self._cache[text] = vec
        return np.vstack([self._cache[t] for t in texts]).astype(np.float32)


def describe(embedder: Embedder) -> dict:
    """Operator-facing summary. Unwraps the cache so the real model shows."""
    inner = getattr(embedder, "inner", embedder)
    out = {
        "embedder": type(inner).__name__,
        "dim": getattr(embedder, "dim", None),
        # The premise of the semantic term is synonymy. HashingEmbedder cannot do
        # synonymy, so flag it rather than let a lexical fallback look like a model.
        "semantic": not isinstance(inner, HashingEmbedder),
    }
    if isinstance(inner, VertexEmbedder):
        out["model"] = inner._model
        out["embed_failures"] = inner.failures
    return out


def default_embedder() -> Embedder:
    """Best available model, deterministic fallback last.

    Order: Vertex (ADC, no extra dependency) -> local sentence-transformers ->
    hashing. Never raises. A missing model degrades retrieval quality; it must
    not take the demo down.

    Set `MOOD_EMBEDDER=hashing` to pin the offline embedder -- CI and the
    retrieval tests want byte-identical vectors and no network, and pinning is
    better than depending on credentials happening to be absent.
    """
    forced = os.environ.get("MOOD_EMBEDDER", "").strip().lower()
    if forced == "hashing":
        return CachedEmbedder(HashingEmbedder())

    if forced in ("", "vertex"):
        try:
            return CachedEmbedder(VertexEmbedder())
        except Exception:
            pass

    try:
        return CachedEmbedder(SentenceTransformerEmbedder())
    except Exception:
        return CachedEmbedder(HashingEmbedder())
