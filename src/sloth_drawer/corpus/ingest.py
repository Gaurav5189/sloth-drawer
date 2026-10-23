"""Reading manual PDFs into pages.

The rule that shapes this module: **a broken file must never abort a batch.**
A corpus of 19 manuals where 3 are broken still has to produce 16 cards, and the
count of skipped files must be visible in the final report — never quietly
dropped (RULES.md 2.4).

So every failure is a *recorded outcome*: a skip with a reason code, not an
exception that escapes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from sloth_drawer.errors import ConfigError, CorpusError, NoTextLayerError


@dataclass(frozen=True)
class Page:
    """One page of a manual.

    ``number`` is 1-indexed, because that is how a manual is cited and how a
    reader counts.
    """

    number: int
    text: str
    source: str


@dataclass(frozen=True)
class Manual:
    """A manual that was read successfully."""

    slug: str
    path: Path
    sha256: str
    pages: tuple[Page, ...]
    #: Pages whose text could not be extracted, with the exception class name.
    unreadable_pages: tuple[tuple[int, str], ...] = field(default=())

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def text(self) -> str:
        """The whole manual as one string, pages separated by a form feed."""
        return "\n\f\n".join(page.text for page in self.pages)


@dataclass(frozen=True)
class Skipped:
    """A file that was not read, and why."""

    path: Path
    reason: str
    detail: str = ""

    def __str__(self) -> str:
        suffix = f" ({self.detail})" if self.detail else ""
        return f"{self.path.name}: {self.reason}{suffix}"


@dataclass(frozen=True)
class IngestResult:
    """Everything that came out of a directory of manuals."""

    manuals: tuple[Manual, ...]
    skipped: tuple[Skipped, ...]

    @property
    def ok(self) -> int:
        return len(self.manuals)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)


def sha256_of(path: Path) -> str:
    """The hash of the source file, used to key the vector index."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_manual(path: Path, slug: str) -> Manual:
    """Read one PDF into pages.

    Raises :class:`NoTextLayerError` when the file is an image-only scan and
    :class:`CorpusError` for everything else that makes it unreadable. A single
    unreadable *page* is not fatal: the manual keeps its other pages and the
    failure is recorded on the manual.
    """
    try:
        reader = PdfReader(str(path))
    except PdfReadError as exc:
        raise CorpusError(f"{path.name} could not be opened: {exc}", reason="corrupt_pdf") from exc
    except Exception as exc:  # noqa: BLE001 - any parser failure is a corrupt file
        raise CorpusError(
            f"{path.name} could not be opened: {type(exc).__name__}", reason="corrupt_pdf"
        ) from exc

    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception as exc:  # noqa: BLE001 - most encrypted files refuse
            raise CorpusError(f"{path.name} is encrypted", reason="encrypted_pdf") from exc

    try:
        raw_pages = list(reader.pages)
    except Exception as exc:  # noqa: BLE001 - a broken page tree is a corrupt file
        raise CorpusError(
            f"{path.name} could not be read: {type(exc).__name__}", reason="corrupt_pdf"
        ) from exc

    if not raw_pages:
        raise CorpusError(f"{path.name} has no pages", reason="empty_pdf")

    pages: list[Page] = []
    unreadable: list[tuple[int, str]] = []
    for index, page in enumerate(raw_pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # noqa: BLE001 - one bad page is not the whole file
            unreadable.append((index, type(exc).__name__))
            continue
        pages.append(Page(number=index, text=text, source=path.name))

    if not pages:
        raise CorpusError(f"{path.name}: every page failed to extract", reason="corrupt_pdf")

    total = sum(len(page.text.strip()) for page in pages)
    if total < 80:
        raise NoTextLayerError(
            f"{path.name} has no text layer ({total} characters over {len(pages)} pages) — "
            f"it is an image-only scan"
        )

    return Manual(
        slug=slug,
        path=path,
        sha256=sha256_of(path),
        pages=tuple(pages),
        unreadable_pages=tuple(unreadable),
    )


def slug_from_filename(path: Path) -> str:
    """A stable identifier for a manual that is not its filename.

    Filenames carry vendor junk (`User-Manual_5500-2.pdf`). The slug is the
    stem, lower-cased, with anything that is not a word character collapsed to
    a dash.
    """
    import re

    stem = path.stem.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")
    return slug or "manual"


def list_pdfs(directory: Path) -> list[Path]:
    """Every PDF in a directory, sorted.

    A directory with no PDFs is a configuration error, not an empty run: the
    user asked for a scan and there is nothing to scan (RULES.md 2.4).
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise ConfigError(f"Manual directory not found: {directory}")

    pdfs = sorted(p for p in directory.glob("*.pdf") if p.is_file())
    if not pdfs:
        raise ConfigError(f"No PDFs found in {directory}")
    return pdfs


def ingest_directory(directory: Path, slugs: dict[str, str] | None = None) -> IngestResult:
    """Read every PDF in a directory.

    ``slugs`` maps a filename to the device slug from the registry, so the
    manual is attributed to the right device. Files with no registry entry are
    still read, under a slug derived from their filename.
    """
    pdfs = list_pdfs(directory)

    manuals: list[Manual] = []
    skipped: list[Skipped] = []

    for path in pdfs:
        slug = (slugs or {}).get(path.name) or slug_from_filename(path)
        try:
            manuals.append(read_manual(path, slug))
        except (CorpusError, NoTextLayerError) as exc:
            skipped.append(Skipped(path=path, reason=exc.reason, detail=str(exc)))

    return IngestResult(manuals=tuple(manuals), skipped=tuple(skipped))
