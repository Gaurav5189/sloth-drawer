"""Tests for page chunking."""

from __future__ import annotations

from sloth_drawer.corpus.chunk import candidate_excerpts, chunk_page
from sloth_drawer.corpus.ingest import Page

PAGE_TEXT = """Section 4.2 Filter Maintenance
The Pre-Carbon filter (Part No. DX-CF14) must be replaced every 2 months.
Replace the Pre-Carbon filter sooner if the FILTER LIFE indicator flashes
red or after 720 hours of continuous operation, whichever occurs first.

Section 4.3 Exterior Care
Wipe the exterior with a dry cloth every 2 weeks. Do not use solvents.
Replace the Pre-Motor filter (Part No. DX-PF07) every 90 days."""


def _page() -> Page:
    return Page(number=7, text=PAGE_TEXT, source="manual.pdf")


def test_a_page_splits_into_chunks_that_keep_the_page_number() -> None:
    chunks = chunk_page(_page())
    assert chunks
    assert all(chunk.page == 7 for chunk in chunks)
    assert all(chunk.source == "manual.pdf" for chunk in chunks)


def test_every_chunk_is_a_verbatim_slice_of_the_page() -> None:
    page = _page()
    for chunk in chunk_page(page):
        assert page.text[chunk.start : chunk.end] == chunk.text


def test_a_heading_becomes_the_section_of_the_chunks_under_it() -> None:
    chunks = chunk_page(_page())
    sections = [chunk.section for chunk in chunks if chunk.section]
    assert any("Filter Maintenance" in (section or "") for section in sections)
    assert any("Exterior Care" in (section or "") for section in sections)


def test_the_heading_is_kept_in_the_chunk_text() -> None:
    chunks = chunk_page(_page())
    assert any("Section 4.2 Filter Maintenance" in chunk.text for chunk in chunks)


def test_an_empty_page_yields_no_chunks() -> None:
    assert chunk_page(Page(number=1, text="   \n  \n", source="m.pdf")) == []


def test_candidate_excerpts_gives_one_excerpt_per_interval_sentence() -> None:
    chunks = chunk_page(_page())
    excerpts: list[str] = []
    for chunk in chunks:
        excerpts.extend(candidate_excerpts(chunk))
    assert any("Pre-Carbon" in excerpt for excerpt in excerpts)
    assert any("Pre-Motor" in excerpt for excerpt in excerpts)


def test_candidate_excerpts_keep_some_context() -> None:
    """An excerpt with no context cannot be turned into a task label."""
    chunks = chunk_page(_page())
    for chunk in chunks:
        for excerpt in candidate_excerpts(chunk):
            assert len(excerpt) > len("every 2 months")
