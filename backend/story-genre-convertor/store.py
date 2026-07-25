"""Every artifact of a run, on disk, under a readable name.

The short pipeline caches only the two expensive outputs — the skeleton and the
prose. Everything in between is thrown away: the rolling summaries, what each
scene claimed it covered, which scenes retried. That was survivable at six
scenes. It is not survivable at three hundred, because the question you will
actually be asking is "where did this go wrong", and the answer lives in the
intermediates.

Two failures in the corpus benchmark make the case. `swap → romance` opened at
what should have been beat 7, and `understudy → comedy` inverted its
protagonist's guilt — and in both, the generator reported full coverage. Nothing
recorded the claim, so there was nothing to inspect afterwards.

A run directory looks like:

    .cache/runs/<run_id>/
      manifest.json          what was asked for, and how it went
      source.txt             exactly what came in
      chunks/000.txt         segmentation output
      skeletons/             chapter-000.json, act-000.json, book.json
      casting.json           the cast, decided once
      outline.json           the chapter plan
      bible.json             the canon, with its full revision log
      scenes/ch000-s00.json  prose, claimed coverage, verified coverage, retries
      report.json            fidelity, per chapter and overall

    python store.py --selftest
    python store.py --list
"""

import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from cache import CACHE_DIR

RUNS_DIR = CACHE_DIR / "runs"


class SceneRecord(BaseModel):
    """One scene, with everything needed to explain it later."""

    scene_id: str
    chapter: str
    beats_assigned: List[str]
    beats_claimed: List[str] = Field(
        default_factory=list, description="What the generator said it delivered."
    )
    beats_verified: List[str] = Field(
        default_factory=list,
        description="What an independent check found on the page. The one to trust.",
    )
    attempts: int = 1
    words: int = 0
    prose: str = ""
    bible_slice: str = Field("", description="Exactly what context this scene was given.")
    facts_added: List[int] = Field(default_factory=list)

    @property
    def overclaimed(self) -> List[str]:
        """Beats the generator claimed but the check could not find.

        This list is the whole reason the record exists.
        """
        return sorted(set(self.beats_claimed) - set(self.beats_verified))

    @property
    def missing(self) -> List[str]:
        return sorted(set(self.beats_assigned) - set(self.beats_verified))


class Manifest(BaseModel):
    run_id: str
    genre: str
    source_words: int
    source_hash: str
    status: str = "running"
    stage: str = ""
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    chunks: int = 0
    error: Optional[str] = None
    notes: List[str] = Field(default_factory=list)


class Store:
    """A run directory. Every write is immediate, so a crash keeps what it had."""

    def __init__(self, run_id: str, root: Optional[Path] = None) -> None:
        self.run_id = run_id
        self.root = (root or RUNS_DIR) / run_id
        for sub in ("", "chunks", "skeletons", "scenes"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    # -- primitives --------------------------------------------------------

    def _path(self, *parts: str) -> Path:
        path = self.root.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def put_json(self, name: str, payload: Any) -> None:
        data = payload.model_dump() if isinstance(payload, BaseModel) else payload
        self._path(name).write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def get_json(self, name: str) -> Optional[dict]:
        path = self.root / name
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except ValueError:
            return None

    def put_text(self, name: str, text: str) -> None:
        self._path(name).write_text(text)

    def get_text(self, name: str) -> Optional[str]:
        path = self.root / name
        return path.read_text() if path.exists() else None

    def has(self, name: str) -> bool:
        return (self.root / name).exists()

    # -- typed helpers -----------------------------------------------------

    def manifest(self) -> Optional[Manifest]:
        raw = self.get_json("manifest.json")
        return Manifest.model_validate(raw) if raw else None

    def set_manifest(self, manifest: Manifest) -> None:
        manifest.updated_at = time.time()
        self.put_json("manifest.json", manifest)

    def touch(self, **fields) -> Optional[Manifest]:
        """Update the manifest in place — status, stage, a note."""
        manifest = self.manifest()
        if manifest is None:
            return None
        notes = fields.pop("note", None)
        for key, value in fields.items():
            setattr(manifest, key, value)
        if notes:
            manifest.notes.append(f"{time.strftime('%H:%M:%S')} {notes}")
        self.set_manifest(manifest)
        return manifest

    def put_chunk(self, index: int, text: str) -> None:
        self.put_text(f"chunks/{index:03d}.txt", text)

    def chunk(self, index: int) -> Optional[str]:
        return self.get_text(f"chunks/{index:03d}.txt")

    def put_scene(self, record: SceneRecord) -> None:
        self.put_json(f"scenes/{record.scene_id}.json", record)

    def scenes(self) -> List[SceneRecord]:
        out: List[SceneRecord] = []
        for path in sorted((self.root / "scenes").glob("*.json")):
            try:
                out.append(SceneRecord.model_validate_json(path.read_text()))
            except ValueError:
                continue
        return out

    # -- diagnosis ---------------------------------------------------------

    def overclaims(self) -> Dict[str, List[str]]:
        """Scenes that said they delivered a beat the check could not find.

        The exact failure that produced `swap → romance` at 38%, invisible until
        somebody wrote it down.
        """
        return {s.scene_id: s.overclaimed for s in self.scenes() if s.overclaimed}

    def summary(self) -> dict:
        scenes = self.scenes()
        return {
            "run_id": self.run_id,
            "scenes": len(scenes),
            "words": sum(s.words for s in scenes),
            "retried": sum(1 for s in scenes if s.attempts > 1),
            "scenes_with_missing_beats": sum(1 for s in scenes if s.missing),
            "overclaimed_beats": sum(len(s.overclaimed) for s in scenes),
        }


def new_run(run_id: str, genre: str, source: str, root: Optional[Path] = None) -> Store:
    """Start a run: record the input before anything can go wrong with it."""
    import hashlib

    store = Store(run_id, root)
    store.put_text("source.txt", source)
    store.set_manifest(
        Manifest(
            run_id=run_id,
            genre=genre,
            source_words=len(source.split()),
            source_hash=hashlib.sha256(source.encode("utf-8")).hexdigest()[:16],
        )
    )
    return store


def list_runs(root: Optional[Path] = None) -> List[Manifest]:
    base = root or RUNS_DIR
    if not base.exists():
        return []
    out: List[Manifest] = []
    for path in sorted(base.iterdir()):
        if not path.is_dir():
            continue
        manifest = Store(path.name, base.parent if root is None else root).manifest()
        if manifest:
            out.append(manifest)
    return sorted(out, key=lambda m: -m.created_at)


# --------------------------------------------------------------------------
# self-test
# --------------------------------------------------------------------------


def _selftest() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        print("a run records its input first")
        store = new_run("test01", "horror", "word " * 500, root=root)
        manifest = store.manifest()
        assert manifest and manifest.source_words == 500
        assert store.get_text("source.txt")
        print(f"  manifest: {manifest.run_id}, {manifest.source_words}w, hash {manifest.source_hash}")

        print("chunks and skeletons round-trip")
        store.put_chunk(0, "chapter one text")
        store.put_chunk(1, "chapter two text")
        store.put_json("skeletons/chapter-000.json", {"beats": [{"id": "b1"}]})
        assert store.chunk(1) == "chapter two text"
        assert store.get_json("skeletons/chapter-000.json")["beats"][0]["id"] == "b1"
        print("  chunks/000.txt, chunks/001.txt, skeletons/chapter-000.json")

        print("scene records keep claimed and verified apart")
        store.put_scene(
            SceneRecord(
                scene_id="ch000-s00",
                chapter="ch000",
                beats_assigned=["b1", "b2"],
                beats_claimed=["b1", "b2"],
                beats_verified=["b1", "b2"],
                words=400,
            )
        )
        # The swap failure, recorded: claimed everything, delivered one.
        store.put_scene(
            SceneRecord(
                scene_id="ch000-s01",
                chapter="ch000",
                beats_assigned=["b3", "b4", "b5"],
                beats_claimed=["b3", "b4", "b5"],
                beats_verified=["b3"],
                attempts=2,
                words=350,
            )
        )
        assert len(store.scenes()) == 2
        overclaims = store.overclaims()
        assert overclaims == {"ch000-s01": ["b4", "b5"]}, overclaims
        print(f"  overclaims caught: {overclaims}")

        print("summary")
        for key, value in store.summary().items():
            print(f"  {key:<26} {value}")

        print("manifest updates in place")
        store.touch(stage="transform", note="scene 4/7")
        store.touch(status="done")
        manifest = store.manifest()
        assert manifest.status == "done" and manifest.stage == "transform"
        assert manifest.notes and "scene 4/7" in manifest.notes[0]
        print(f"  status={manifest.status} stage={manifest.stage} notes={manifest.notes}")

        print("a crashed run keeps what it had")
        broken = new_run("test02", "comedy", "word " * 300, root=root)
        broken.put_chunk(0, "partial")
        broken.touch(status="error", error="quota exhausted")
        assert broken.manifest().error == "quota exhausted"
        assert broken.chunk(0) == "partial"
        print("  chunk written before the failure is still readable")

        print("runs are listable")
        runs = list_runs(root)
        assert len(runs) == 2, [r.run_id for r in runs]
        print(f"  {[(r.run_id, r.status) for r in runs]}")

    print()
    print("store OK")
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run artifacts on disk.")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--list", action="store_true", help="list runs in the cache")
    parser.add_argument("--show", help="summarise one run by id")
    parser.add_argument("--purge", help="delete one run by id")
    args = parser.parse_args()

    if args.selftest:
        raise SystemExit(_selftest())
    if args.list:
        for manifest in list_runs():
            print(
                f"  {manifest.run_id:<20} {manifest.genre:<10} {manifest.status:<8} "
                f"{manifest.source_words:>7}w  {manifest.chunks} chunks"
            )
        raise SystemExit(0)
    if args.show:
        store = Store(args.show)
        print(json.dumps(store.summary(), indent=2))
        overclaims = store.overclaims()
        if overclaims:
            print("\noverclaimed beats (generator said delivered, check disagreed):")
            for scene, beats in overclaims.items():
                print(f"  {scene}: {', '.join(beats)}")
        raise SystemExit(0)
    if args.purge:
        shutil.rmtree(RUNS_DIR / args.purge, ignore_errors=True)
        print(f"removed {args.purge}")
        raise SystemExit(0)
    parser.error("give --selftest, --list, --show ID or --purge ID")
