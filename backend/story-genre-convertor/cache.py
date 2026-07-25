"""Disk cache for the two expensive artifacts: skeletons and rewrites.

Lifted out of calibrate.py so pipeline.py can use it too. A five-genre run is
five rewrites plus five re-extractions plus five alignments; nobody should pay
for that twice, and nobody should ever watch a judge sit through a cold run.

Keys are caller-supplied and human-readable on purpose — you want to be able to
look in .cache/ and see `reveal__horror.txt` rather than a hash.
"""

import os
from pathlib import Path
from typing import Callable

from models import StorySkeleton

# Relocatable so the HTTP service can point it at a writable path. On Cloud Run
# the container filesystem is in-memory and ephemeral, so a cache there buys
# instant repeat answers within an instance's life and nothing beyond that.
CACHE_DIR = Path(os.environ.get("CACHE_DIR") or (Path(__file__).parent / ".cache"))


def _path(key: str, suffix: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{key}{suffix}"


def cached_skeleton(key: str, build: Callable[[], StorySkeleton], use_cache: bool = True) -> StorySkeleton:
    """Return a cached skeleton, or build and store one."""
    path = _path(key, ".json")
    if use_cache and path.exists():
        return StorySkeleton.model_validate_json(path.read_text())
    skeleton = build()
    path.write_text(skeleton.model_dump_json(indent=2))
    return skeleton


def cached_text(key: str, build: Callable[[], str], use_cache: bool = True) -> str:
    """Return cached prose, or build and store it."""
    path = _path(key, ".txt")
    if use_cache and path.exists():
        return path.read_text()
    text = build()
    path.write_text(text)
    return text
