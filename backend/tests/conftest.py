"""Shared pytest setup.

Pins the mood index to the offline embedder for the whole suite. Without this,
`default_embedder()` prefers Vertex, so on a developer machine that happens to
have ADC credentials the tests would make real embedding calls at import time —
slow, billable, and non-deterministic, with retrieval assertions that quietly
depend on a model version. Tests should assert the ranking logic, not a model.

Set before any `app.mood` import so the module-level default is already correct.
"""

from __future__ import annotations

import os

os.environ.setdefault("MOOD_EMBEDDER", "hashing")
