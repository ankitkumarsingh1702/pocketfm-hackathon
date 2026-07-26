#!/usr/bin/env python3
"""
playlist_extractor.py — Extract every track from a YouTube / YouTube Music
playlist into a JSON file, using only the playlist URL.

No API key and no login required: it uses yt-dlp to read the public playlist.

One-time setup:
    pip install -U yt-dlp

Usage:
    python playlist_extractor.py "https://music.youtube.com/playlist?list=XXXX"
    python playlist_extractor.py "https://www.youtube.com/playlist?list=XXXX" -o songs.json
    python playlist_extractor.py "URL" --full     # slower; adds artist/album/track when available
    python playlist_extractor.py "URL" --print     # also print the list to the terminal
    python playlist_extractor.py                    # no URL given -> prompts for one

Output JSON shape:
    {
      "playlist": { "title": ..., "id": ..., "uploader": ..., "url": ..., "source": ... },
      "count": 42,
      "tracks": [
        { "index": 1, "title": ..., "artist": ..., "album": ..., "track": ...,
          "duration_seconds": 213, "duration": "3:33", "video_id": ..., "url": ... },
        ...
      ]
    }
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def _fail(msg: str, code: int = 1) -> None:
    """Print an error to stderr and exit."""
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(code)


def _import_ytdlp():
    """Import yt-dlp, or exit with an install hint."""
    try:
        from yt_dlp import YoutubeDL

        return YoutubeDL
    except ImportError:
        _fail("yt-dlp is not installed. Install it with:\n\n    pip install -U yt-dlp\n")


def _hms(seconds) -> str | None:
    """Format a duration in seconds as 'M:SS' (or 'H:MM:SS')."""
    if not seconds:
        return None
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _clean_artist(entry: dict) -> str | None:
    """Best-effort artist name.

    YouTube Music tags real music with an `artist` field (only on full
    extraction). Otherwise fall back to the uploader/channel, stripping the
    auto-generated ' - Topic' suffix YouTube Music uses for artist channels.
    """
    for key in ("artist", "creator", "uploader", "channel"):
        val = entry.get(key)
        if val:
            val = re.sub(r"\s*-\s*Topic$", "", str(val)).strip()
            if val:
                return val
    return None


def _normalize(entry: dict, index: int) -> dict:
    """Turn a raw yt-dlp entry into a clean track record."""
    vid = entry.get("id")
    url = entry.get("url") or entry.get("webpage_url")
    if url and not str(url).startswith("http") and vid:
        url = f"https://www.youtube.com/watch?v={vid}"
    duration = entry.get("duration")
    return {
        "index": index,
        "title": entry.get("title"),
        "artist": _clean_artist(entry),
        "album": entry.get("album"),
        "track": entry.get("track"),
        "duration_seconds": duration,
        "duration": _hms(duration),
        "video_id": vid,
        "url": url,
    }


def _safe_filename(name: str) -> str:
    """Make a string safe to use as a filename across OSes."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name).strip().rstrip(".")
    return name or "playlist"


def extract(url: str, full: bool = False) -> dict:
    """Read the playlist at `url` and return a structured dict of its tracks.

    When `full` is False (default) we use flat extraction — fast, one network
    read for the whole playlist, no per-video resolution. When True, each video
    is resolved so YouTube Music's artist/album/track fields are populated
    (much slower on large playlists).
    """
    YoutubeDL = _import_ytdlp()
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist" if not full else False,
        "ignoreerrors": True,  # skip private/deleted items instead of aborting
    }

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:  # network error, unsupported URL, etc.
        _fail(f"failed to read the playlist: {exc}")

    if info is None:
        _fail("could not read that URL (private playlist, bad link, or network issue).")

    entries = info.get("entries")
    if entries is None:
        entries = [info]  # a single video URL, not a playlist

    tracks: list[dict] = []
    for e in entries:
        if not e:
            continue  # None => a skipped unavailable/private entry (ignoreerrors)
        tracks.append(_normalize(e, len(tracks) + 1))

    return {
        "playlist": {
            "title": info.get("title"),
            "id": info.get("id"),
            "uploader": info.get("uploader") or info.get("channel"),
            "url": info.get("webpage_url") or url,
            "source": info.get("extractor_key"),
        },
        "count": len(tracks),
        "tracks": tracks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract all tracks from a YouTube / YouTube Music playlist into JSON."
    )
    parser.add_argument(
        "url",
        nargs="?",
        help="Playlist URL (YouTube or YouTube Music). If omitted, you'll be prompted.",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output JSON path (default: '<playlist title>.json').",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Resolve each video for artist/album/track metadata (slower).",
    )
    parser.add_argument(
        "--print",
        dest="show",
        action="store_true",
        help="Also print 'Title — Artist' to the console.",
    )
    args = parser.parse_args()

    url = (args.url or input("Playlist URL: ")).strip()
    if not url:
        _fail("no URL provided.")

    print(
        "Reading playlist" + (" (full metadata — slower)" if args.full else "") + " …",
        file=sys.stderr,
    )
    data = extract(url, full=args.full)

    if data["count"] == 0:
        _fail("no tracks found — is the playlist public and non-empty?")

    title = data["playlist"]["title"] or "playlist"
    out_path = Path(args.output) if args.output else Path(f"{_safe_filename(title)}.json")
    if out_path.parent != Path("."):
        out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"✓ {data['count']} tracks -> {out_path}", file=sys.stderr)

    if args.show:
        for t in data["tracks"]:
            artist = f" — {t['artist']}" if t["artist"] else ""
            print(f"{t['index']:>3}. {t['title']}{artist}")


if __name__ == "__main__":
    main()
