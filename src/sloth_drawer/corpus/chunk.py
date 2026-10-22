"""Splitting pages into chunks that remember where they came from.

A chunk is the unit the model sees. Three things must survive the split:

*   the **page number**, because a citation without a page is not a citation;
*   the **section heading**, because "4.2 Filter Maintenance" tells the reader
    what kind of instruction they are looking at;
*   the **character offsets** back into the page, so any text can be
    re-located in the source and checked.

The chunk text is always a verbatim slice of the page text. That is what lets
the verifier take a fragment the model points at and find it again in the
original.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sloth_drawer.corpus import prefilter
from sloth_drawer.corpus.ingest import Page

#: Soft cap on chunk size. Small enough that a chunk is one topic, large
#: enough that the model has the context it needs to name a task.
MAX_CHUNK_CHARS = 1400

#: Chunks shorter than this are merged forward: a two-line fragment rarely
#: states an interval on its own, and it costs a model call to ask.
MIN_CHUNK_CHARS = 200

#: Headings look like this in a real manual.
_HEADING_PATTERNS = (
    re.compile(r"^\d+(?:\.\d+)*\s+[A-Z][^\n]{2,70}$"),
    re.compile(r"^(?:SECTION|Section)\s+\d+(?:\.\d+)*[.:]?\s+\S.{0,70}$"),
    re.compile(r"^(?:CHAPTER|Chapter)\s+\d+[.:]?\s+\S.{0,70}$"),
    re.compile(r"^[A-Z][A-Z0-9 \-/&(),.']{4,60}$"),
)


@dataclass(frozen=True)
class Chunk:
    """A slice of one page of one manual."""

    text: str
    page: int
    section: str | None
    start: int
    end: int
    source: str

    @property
    def length(self) -> int:
        return len(self.text)

    @property
    def clean_text(self) -> str:
        """The chunk text with surrounding whitespace removed."""
        return self.text.strip()


def looks_like_heading(line: str) -> bool:
    """Whether a line reads like a section heading rather than body text.

    Deliberately conservative. A false positive costs a slightly wrong section
    label; a false negative loses the section entirely, and the heading is
    worth more than the precision.
    """
    stripped = line.strip()
    if not stripped or len(stripped) > 72:
        return False
    # A sentence is not a heading. All-caps abbreviations are exempt.
    if (
        stripped.endswith((".", ",", ";"))
        and not stripped.endswith("..")
        and not stripped.isupper()
    ):
        return False
    return any(pattern.match(stripped) for pattern in _HEADING_PATTERNS)


def _line_spans(text: str) -> list[tuple[int, int, str]]:
    """Every line of the text with its character offsets."""
    spans: list[tuple[int, int, str]] = []
    cursor = 0
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\n")
        spans.append((cursor, cursor + len(stripped), stripped))
        cursor += len(line)
    return spans


def chunk_page(page: Page) -> list[Chunk]:
    """Split one page into chunks.

    A heading starts a new section and is carried forward, so every chunk knows
    which section it belongs to even when the heading itself falls in an
    earlier chunk.
    """
    text = page.text
    if not text.strip():
        return []

    spans = _line_spans(text)
    section: str | None = None
    # (start, end, section-as-it-was-when-this-block-started)
    blocks: list[tuple[int, int, str | None]] = []
    block_start: int | None = None
    block_end = 0

    def close_block() -> None:
        nonlocal block_start, block_end
        if block_start is not None and block_end > block_start:
            blocks.append((block_start, block_end, section))
        block_start = None

    for start, end, line in spans:
        if not line.strip():
            close_block()
            continue
        if looks_like_heading(line):
            close_block()
            section = line.strip()
        if block_start is None:
            block_start = start
        block_end = end
    close_block()

    if not blocks:
        return []

    # Merge blocks into chunks, never exceeding the cap and never leaving a
    # fragment below the floor.
    chunks: list[Chunk] = []
    current_start: int | None = None
    current_end = 0
    current_section: str | None = None

    def flush() -> None:
        nonlocal current_start
        if current_start is None:
            return
        chunks.append(
            Chunk(
                text=text[current_start:current_end],
                page=page.number,
                section=current_section,
                start=current_start,
                end=current_end,
                source=page.source,
            )
        )
        current_start = None

    for start, end, block_section in blocks:
        if current_start is None:
            current_start, current_section = start, block_section
        elif block_section != current_section:
            # A new section heading starts a new chunk, so a citation's
            # section always matches the text it points at.
            flush()
            current_start, current_section = start, block_section
        current_end = end
        if (current_end - current_start) > MAX_CHUNK_CHARS:
            flush()
    flush()
    return chunks


def chunk_manual(pages: tuple[Page, ...]) -> list[Chunk]:
    """Chunk every page of a manual."""
    chunks: list[Chunk] = []
    for page in pages:
        chunks.extend(chunk_page(page))
    return chunks


def candidate_excerpts(chunk: Chunk) -> list[str]:
    """One short excerpt per interval-bearing sentence in the chunk.

    This is where "find every interval" stops being the model's job. The code
    decides which sentences look like they state an interval and builds one
    excerpt around each, so the model is asked one question per candidate and
    never has to choose what to look at next (C5, and RULES.md 4.3).

    The excerpt keeps one neighbour on each side. Context is what lets the
    model name the task ("Pre-Carbon filter replacement" rather than "filter"),
    and it keeps the quote it points at inside a readable stretch of text.
    """
    sentences = prefilter.split_sentences(chunk.text)
    excerpts: list[str] = []
    seen: set[str] = set()

    for candidate in prefilter.candidate_sentences(chunk.text):
        key = re.sub(r"\s+", " ", candidate).strip().lower()
        if key in seen:
            continue
        seen.add(key)

        index = next(
            (i for i, sentence in enumerate(sentences) if sentence == candidate),
            0,
        )
        window = sentences[max(0, index - 1) : index + 2]
        excerpts.append(" ".join(window))
    return excerpts
