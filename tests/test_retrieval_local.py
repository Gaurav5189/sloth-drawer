"""Tests for the local FTS5 retrieval backend."""

from __future__ import annotations

import sqlite3

from sloth_drawer.retrieval.local import LocalRetriever


def _retriever() -> LocalRetriever:
    connection = sqlite3.connect(":memory:")
    return LocalRetriever(connection)


def _index(retriever: LocalRetriever) -> None:
    retriever.index(
        "sha-abc",
        "duramax-900",
        [
            (
                12,
                "4.2 Filter Maintenance",
                "The Pre-Carbon filter (Part No. DX-CF14) must be replaced every 2 months.",
            ),
            (13, "4.3 Exterior Care", "Wipe the exterior with a dry cloth every 2 weeks."),
            (
                14,
                "5.1 Spare Parts",
                "The HEPA filter (Part No. DX-HF22) should be replaced every 12 months.",
            ),
        ],
    )


def test_a_part_number_is_matched_exactly() -> None:
    """The reason this backend uses the trigram tokenizer."""
    retriever = _retriever()
    _index(retriever)
    hits = retriever.search("DX-CF14", k=5)
    assert hits
    assert "DX-CF14" in hits[0].content
    assert hits[0].page == 12
    assert hits[0].backend == "local"


def test_a_rare_word_is_matched() -> None:
    retriever = _retriever()
    _index(retriever)
    hits = retriever.search("Exterior", k=5)
    assert hits
    assert hits[0].page == 13


def test_the_citation_fields_come_back_with_the_hit() -> None:
    retriever = _retriever()
    _index(retriever)
    hit = retriever.search("DX-HF22", k=5)[0]
    assert hit.manual_sha == "sha-abc"
    assert hit.page == 14
    assert hit.section == "5.1 Spare Parts"


def test_an_empty_result_is_not_an_error() -> None:
    retriever = _retriever()
    _index(retriever)
    assert retriever.search("turbinebladeassembly", k=5) == []


def test_a_query_shorter_than_a_trigram_returns_nothing() -> None:
    retriever = _retriever()
    _index(retriever)
    assert retriever.search("DX", k=5) == []


def test_a_query_with_a_quote_does_not_break_the_index() -> None:
    retriever = _retriever()
    _index(retriever)
    assert retriever.search('the "Pre-Carbon" filter', k=5) is not None


def test_the_limit_is_respected() -> None:
    retriever = _retriever()
    _index(retriever)
    assert len(retriever.search("filter", k=1)) == 1
