"""Tiny JSON file cache for LLM responses.

Keeps live demos instant: once a persona has reacted to a given story under a
given provider, the reaction is stored on disk and replayed on the next run
instead of re-hitting the LLM. All IO is best-effort — the cache never raises,
so a broken/unwritable cache dir degrades to "no cache" rather than crashing
the engine.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.config import BACKEND_DIR


class Cache:
    """A content-addressed JSON cache rooted at ``root``.

    ``root`` may be absolute or relative; relative paths resolve against the
    ``backend/`` directory so ``.cache`` lands next to ``pyproject.toml``.
    """

    def __init__(self, root: str) -> None:
        path = Path(root)
        if not path.is_absolute():
            path = BACKEND_DIR / path
        self.root = path
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Unwritable location — get()/set() will simply no-op.
            pass

    def make_key(self, *parts: object) -> str:
        """Return a stable 24-char hex key derived from ``parts``."""
        raw = "::".join(str(p) for p in parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> dict | None:
        """Return the cached dict for ``key``, or ``None`` on miss/error."""
        try:
            with self._path(key).open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None

    def set(self, key: str, value: dict) -> None:
        """Persist ``value`` under ``key``. Silently ignores IO errors."""
        try:
            with self._path(key).open("w", encoding="utf-8") as fh:
                json.dump(value, fh, ensure_ascii=False)
        except (OSError, TypeError, ValueError):
            pass
