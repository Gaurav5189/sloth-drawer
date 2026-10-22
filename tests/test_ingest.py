"""Tests for PDF ingestion and its error policy."""

from __future__ import annotations

from pathlib import Path

import pytest

from sloth_drawer.corpus.ingest import (
    ingest_directory,
    read_manual,
    sha256_of,
    slug_from_filename,
)
from sloth_drawer.errors import ConfigError, CorpusError

CORPUS = Path(__file__).resolve().parents[1] / "data" / "manuals"
HAS_PDFS = CORPUS.is_dir() and any(CORPUS.glob("*.pdf"))


def _manual(name: str) -> Path:
    return CORPUS / name


@pytest.mark.skipif(not HAS_PDFS, reason="the corpus is not downloaded")
def test_a_real_manual_is_read() -> None:
    manual = read_manual(_manual("honeywell-hpa8350.pdf"), "honeywell-hpa8350")
    assert manual.page_count > 0
    assert manual.pages[0].number == 1
    assert manual.sha256
    assert len(manual.text) > 1000


@pytest.mark.skipif(
    not _manual("medify-ma-25.pdf").exists(),
    reason="the medify-ma-25 pdf is missing",
)
def test_a_manual_whose_page_fails_still_yields_its_other_pages() -> None:
    """One broken page is not a broken manual."""
    manual = read_manual(_manual("medify-ma-25.pdf"), "medify-ma-25")
    assert manual.page_count > 0
    assert manual.unreadable_pages


@pytest.mark.skipif(not HAS_PDFS, reason="the corpus is not downloaded")
def test_the_whole_corpus_is_readable() -> None:
    result = ingest_directory(CORPUS)
    assert result.ok >= 15
    assert all(manual.page_count > 0 for manual in result.manuals)


def test_a_missing_directory_is_a_configuration_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        ingest_directory(tmp_path / "nope")


def test_a_directory_without_pdfs_is_a_configuration_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="No PDFs"):
        ingest_directory(tmp_path)


def test_a_broken_file_is_skipped_and_recorded(tmp_path: Path) -> None:
    (tmp_path / "broken.pdf").write_bytes(b"this is not a pdf")
    with pytest.raises(CorpusError) as caught:
        read_manual(tmp_path / "broken.pdf", "broken")
    assert caught.value.reason in ("corrupt_pdf", "empty_pdf")


def test_the_slug_is_stable_and_readable() -> None:
    assert slug_from_filename(Path("User-Manual_5500-2.pdf")) == "user-manual-5500-2"
    assert slug_from_filename(Path("manual.pdf")) == "manual"


def test_the_hash_is_the_hash(tmp_path: Path) -> None:
    target = tmp_path / "x.bin"
    target.write_bytes(b"hello")
    assert len(sha256_of(target)) == 64
