"""Split a long text into chapter-sized chunks. Deterministic, zero tokens.

Stage 0 of the long-form pipeline. Everything downstream is parallel over the
output of this, so getting it wrong is expensive: a chunk that cuts mid-scene
produces a chapter skeleton with a beat that starts nowhere and an edge pointing
at nothing.

Two strategies, in order of preference:

  MARKERS   The text says where its chapters are. Trust it.
  WINDOW    It does not. Fall back to accumulating paragraphs up to a target
            size, breaking only at a blank line, never mid-paragraph.

    python segment.py --selftest
    python segment.py path/to/novel.txt
"""

import argparse
import re
import sys
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

# A chapter's worth of prose. Small enough that extraction stays sharp, large
# enough that a chunk contains whole scenes rather than fragments.
TARGET_WORDS = 2500
MIN_WORDS = 400

# "Chapter 4", "CHAPTER IV", "4.", "Part Two", "* * *" — the shapes a plain-text
# novel actually uses. Anchored to a line of its own so a mention of "chapter"
# inside a sentence never splits anything.
MARKER = re.compile(
    r"^\s*(?:"
    r"chapter\s+[\divxlc]+"
    r"|part\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
    r"|book\s+[\divxlc]+"
    r"|[\divxlc]{1,4}\s*[.\)]"
    r"|\*\s*\*\s*\*"
    r"|#{1,3}\s+\S.*"
    r")\s*$",
    re.IGNORECASE,
)


class Chunk(BaseModel):
    """One unit of extraction."""

    index: int
    title: Optional[str] = Field(None, description="The marker line, when there was one.")
    text: str
    words: int
    start_line: int

    @property
    def label(self) -> str:
        return self.title or f"chunk {self.index + 1}"


def _mk(index: int, title: Optional[str], lines: List[str], start_line: int) -> Chunk:
    text = "\n".join(lines).strip()
    return Chunk(index=index, title=title, text=text, words=len(text.split()), start_line=start_line)


def by_markers(text: str) -> List[Chunk]:
    """Split on chapter markers. Returns [] when the text has none worth using."""
    lines = text.splitlines()
    hits = [i for i, line in enumerate(lines) if MARKER.match(line)]
    if not hits:
        return []

    chunks: List[Chunk] = []
    # Anything before the first marker is front matter or an untitled opening.
    bounds = [(None, 0)] + [(lines[i], i) for i in hits]
    for position, (title, start) in enumerate(bounds):
        end = bounds[position + 1][1] if position + 1 < len(bounds) else len(lines)
        body = lines[start + (1 if title else 0) : end]
        if not any(line.strip() for line in body):
            continue
        chunks.append(_mk(len(chunks), title.strip() if title else None, body, start))
    # One marker that yields a single chunk is a stray match, not structure.
    return chunks if len(chunks) >= 2 else []


def _split_on_sentences(block: str, target_words: int) -> List[str]:
    """Break one oversized paragraph into target-sized pieces at sentence ends.

    Returns the block untouched when it has no sentence boundaries to use —
    better one huge chunk than a sentence cut in half.
    """
    # Fixed-width lookbehind (one char) with any closing quote/bracket consumed
    # after it — Python's re rejects a variable-width lookbehind.
    sentences = re.split(r"(?<=[.!?])[\"')\]]*\s+", block.strip())
    if len(sentences) < 2:
        return [block]

    pieces: List[str] = []
    current: List[str] = []
    count = 0
    for sentence in sentences:
        words = len(sentence.split())
        if current and count + words > target_words:
            pieces.append(" ".join(current))
            current, count = [], 0
        current.append(sentence)
        count += words
    if current:
        pieces.append(" ".join(current))
    return pieces


def by_window(text: str, target_words: int = TARGET_WORDS) -> List[Chunk]:
    """Accumulate paragraphs to roughly `target_words`, breaking on blank lines.

    Never splits a paragraph. A chapter boundary in the wrong place costs one bad
    skeleton; a sentence boundary in the wrong place costs a broken sentence in
    two of them.
    """
    paragraphs: List[str] = []
    for block in re.split(r"\n\s*\n", text):
        if not block.strip():
            continue
        # "Never split a paragraph" needs an escape hatch: some texts have no
        # blank lines at all, and one 4,000-word block must be split somewhere.
        # Sentence boundaries are the least-bad place.
        if len(block.split()) > target_words * 1.5:
            paragraphs.extend(_split_on_sentences(block, target_words))
        else:
            paragraphs.append(block)

    chunks: List[Chunk] = []
    current: List[str] = []
    count = 0
    line_no = 0
    start_line = 0

    for paragraph in paragraphs:
        words = len(paragraph.split())
        if current and count + words > target_words:
            chunks.append(_mk(len(chunks), None, current, start_line))
            current, count, start_line = [], 0, line_no
        current.append(paragraph)
        count += words
        line_no += paragraph.count("\n") + 2

    if current:
        chunks.append(_mk(len(chunks), None, current, start_line))
    return chunks


def _merge_runts(chunks: List[Chunk], min_words: int = MIN_WORDS) -> List[Chunk]:
    """Fold undersized chunks into their neighbour.

    A 40-word chapter break produces a skeleton with one beat and no causality,
    which then pollutes the reduction upward. Better to attach it to the chapter
    it belongs to.
    """
    if len(chunks) < 2:
        return chunks
    merged: List[Chunk] = []
    for chunk in chunks:
        if merged and chunk.words < min_words:
            previous = merged[-1]
            merged[-1] = Chunk(
                index=previous.index,
                title=previous.title,
                text=previous.text + "\n\n" + chunk.text,
                words=previous.words + chunk.words,
                start_line=previous.start_line,
            )
            continue
        merged.append(chunk)
    return [
        Chunk(index=i, title=c.title, text=c.text, words=c.words, start_line=c.start_line)
        for i, c in enumerate(merged)
    ]


def _split_oversized(chunks: List[Chunk], target: int) -> List[Chunk]:
    """A 'chapter' far over target gets windowed back down to target.

    Windowing at the *limit* rather than the target is a trap: a 4,000-word
    chapter against a 3,600 limit splits into 3,600 + 400, and the 400 is then a
    runt that merges straight back. Split to the target, not to the threshold.
    """
    limit = int(target * 1.5)
    out: List[Chunk] = []
    for chunk in chunks:
        if chunk.words <= limit:
            out.append(chunk)
            continue
        for part, piece in enumerate(by_window(chunk.text, target)):
            title = f"{chunk.title} ({part + 1})" if chunk.title else None
            out.append(
                Chunk(
                    index=len(out),
                    title=title,
                    text=piece.text,
                    words=piece.words,
                    start_line=chunk.start_line,
                )
            )
    return [
        Chunk(index=i, title=c.title, text=c.text, words=c.words, start_line=c.start_line)
        for i, c in enumerate(out)
    ]


def segment(text: str, target_words: int = TARGET_WORDS) -> List[Chunk]:
    """Chunk `text`, preferring the author's own chapter breaks."""
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []

    chunks = by_markers(text) or by_window(text, target_words)

    # Merge first, then split. The other order lets a merged pair exceed the
    # limit with nothing left to catch it — which is how a book with dividers
    # near the end came back as one 4,000-word chunk.
    chunks = _merge_runts(chunks)
    chunks = _split_oversized(chunks, target_words)
    return _merge_runts(chunks)


# --------------------------------------------------------------------------
# self-test: pure text handling, so it runs with no credentials and no network
# --------------------------------------------------------------------------


def _selftest() -> int:
    def para(word: str, n: int) -> str:
        return " ".join([word] * n)

    print("markers")
    marked = "\n\n".join(
        [
            "Chapter 1",
            para("alpha", 600),
            "Chapter 2",
            para("bravo", 600),
            "Chapter 3",
            para("charlie", 600),
        ]
    )
    chunks = segment(marked)
    assert len(chunks) == 3, [c.label for c in chunks]
    assert [c.title for c in chunks] == ["Chapter 1", "Chapter 2", "Chapter 3"]
    assert "bravo" in chunks[1].text and "alpha" not in chunks[1].text
    print(f"  three chapters -> {[c.label for c in chunks]}")

    print("  markdown headings and '* * *' also recognised")
    assert len(segment("\n\n".join(["## One", para("a", 500), "## Two", para("b", 500)]))) == 2
    assert len(segment("\n\n".join([para("a", 500), "* * *", para("b", 500)]))) == 2

    print("no markers -> windowing")
    plain = "\n\n".join(para(f"w{i}", 400) for i in range(10))
    chunks = segment(plain, target_words=1000)
    assert len(chunks) >= 3, len(chunks)
    assert all(c.words <= 1400 for c in chunks), [c.words for c in chunks]
    print(f"  4000 words at target 1000 -> {len(chunks)} chunks {[c.words for c in chunks]}")

    print("nothing is lost or reordered")
    original = " ".join(plain.split())
    rebuilt = " ".join(" ".join(c.text for c in chunks).split())
    assert rebuilt == original, "windowing dropped or reordered text"
    print("  every word preserved, in order")

    print("paragraphs are not split unless they have to be")
    normal = "\n\n".join([para("a", 300), para("b", 300)])
    assert len(segment(normal, target_words=1000)) == 1, "paragraphs under target stay together"
    # No sentence boundaries anywhere: better one huge chunk than a broken sentence.
    assert len(segment(para("x", 3000), target_words=500)) == 1
    print("  a 3000-word block with no sentence ends stays whole")
    # With sentence ends, an oversized block is split at them.
    sentences = " ".join(f"{para('s', 40)}." for _ in range(30))
    chunks = segment(sentences, target_words=400)
    assert len(chunks) > 1, "an oversized paragraph with sentences must be split"
    assert all(c.text.rstrip().endswith(".") for c in chunks), "split mid-sentence"
    print(f"  a 1200-word block with sentence ends -> {len(chunks)} chunks, none cut mid-sentence")

    print("dividers near the end do not collapse the whole text")
    # The real failure: markers at the tail gave [huge, tiny, tiny], the tinies
    # merged back, and the result was one oversized chunk.
    prose = " ".join(f"{para('a', 30)}." for _ in range(130))  # ~4000 words, real sentences
    lopsided = "\n\n".join([prose, "***", para("b", 60), "***", para("c", 60)])
    chunks = segment(lopsided, target_words=1800)
    assert len(chunks) > 1, "an oversized chunk survived merging"
    assert all(c.words <= 1800 * 1.5 for c in chunks), [c.words for c in chunks]
    print(f"  4000w + two 60w tails at target 1800 -> {[c.words for c in chunks]}")

    print("runt chapters get folded in")
    runty = "\n\n".join(["Chapter 1", para("a", 600), "Chapter 2", "tiny", "Chapter 3", para("c", 600)])
    chunks = segment(runty)
    assert all(c.words >= MIN_WORDS for c in chunks), [c.words for c in chunks]
    print(f"  {[c.words for c in chunks]} — no chunk under {MIN_WORDS} words")

    print("oversized chapters get windowed")
    huge = "\n\n".join(["Chapter 1", "\n\n".join(para("h", 500) for _ in range(20))])
    chunks = segment(huge, target_words=2000)
    assert len(chunks) > 1, "a 10k-word chapter must be split"
    print(f"  a 10,000-word chapter -> {len(chunks)} chunks")

    print("edge cases")
    assert segment("") == []
    assert len(segment(para("solo", 50))) == 1
    print("  empty text and one short paragraph both handled")

    print()
    print("segmentation OK")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chunk a long text for extraction.")
    parser.add_argument("path", nargs="?", help="a .txt file")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--target", type=int, default=TARGET_WORDS)
    args = parser.parse_args()

    if args.selftest:
        raise SystemExit(_selftest())
    if not args.path:
        parser.error("give a path, or --selftest")

    text = Path(args.path).read_text()
    chunks = segment(text, args.target)
    total = sum(c.words for c in chunks)
    print(f"{len(text.split())} words -> {len(chunks)} chunks ({total} words retained)")
    for chunk in chunks:
        preview = " ".join(chunk.text.split()[:12])
        print(f"  {chunk.index:>3}  {chunk.words:>5}w  {chunk.label:<24} {preview}…")
