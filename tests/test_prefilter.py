"""Tests for the deterministic pre-filter."""

from __future__ import annotations

import pytest

from sloth_drawer.corpus import prefilter
from sloth_drawer.extract.verify import parse_interval


@pytest.mark.parametrize(
    "text",
    [
        "The Pre-Carbon filter must be replaced every 2 months.",
        "Clean the filter every 2 weeks.",
        "Replace the filter every 90 days.",
        "Service the unit every 12 months.",
        "Descale the tank every 3 months.",
    ],
)
def test_interval_language_is_recognised(text: str) -> None:
    score, matches = prefilter.score_text(text)
    assert score >= prefilter.DEFAULT_THRESHOLD
    assert matches


@pytest.mark.parametrize(
    "text",
    [
        "Do not use solvents.",
        "Wipe the exterior with a dry cloth.",
        "Plug the unit into the wall outlet.",
        "The front panel may be cleaned with a mild detergent solution.",
    ],
)
def test_ordinary_prose_is_not_a_candidate(text: str) -> None:
    assert prefilter.is_candidate(text) is False


def test_a_bare_cycle_plus_a_maintenance_verb_is_a_candidate() -> None:
    """Manuals express cycles in tables, not only as "every N months"."""
    assert prefilter.is_candidate("Pre-Carbon filter | 6 months | Replacement") is True


def test_the_score_does_not_grow_with_repetition() -> None:
    once, _ = prefilter.score_text("Replace the filter every 3 months.")
    twice, _ = prefilter.score_text("Replace the filter every 3 months. Replace it every 3 months.")
    assert once == twice


def test_candidate_sentences_picks_only_the_interval_bearing_ones() -> None:
    text = (
        "Section 4.2 Filter Maintenance\n"
        "The Pre-Carbon filter must be replaced every 2 months.\n"
        "Do not wash the Pre-Carbon filter.\n"
        "The HEPA filter should be replaced every 12 months."
    )
    candidates = prefilter.candidate_sentences(text)
    assert len(candidates) == 2
    assert any("Pre-Carbon" in c for c in candidates)
    assert any("HEPA" in c for c in candidates)
    assert not any("Do not wash" in c for c in candidates)


def test_a_sentence_that_appears_twice_is_only_offered_once() -> None:
    line = "The Pre-Carbon filter must be replaced every 2 months."
    assert len(prefilter.candidate_sentences(f"{line}\n{line}")) == 1


def test_hour_only_cycles_are_not_maintenance_intervals() -> None:
    """A filter does not need replacing every 8 hours; a display does."""
    text = "The unit enters sleep mode after 8 hours of continuous operation."
    assert prefilter.candidate_sentences(text) == []


def test_daily_cycles_below_a_week_are_not_maintenance_intervals() -> None:
    assert prefilter.candidate_sentences("The sensor reads every 2 days.") == []
    assert prefilter.candidate_sentences("The sensor reads every 14 days.") != []


def test_split_sentences_keeps_table_rows_whole() -> None:
    text = "Header row\nPre-Carbon filter | 6 months | Replacement\nAnother row"
    assert prefilter.split_sentences(text) == [
        "Header row",
        "Pre-Carbon filter | 6 months | Replacement",
        "Another row",
    ]


def test_split_sentences_splits_prose() -> None:
    text = "Replace the filter every 2 months. Do not wash it. Wipe the case."
    assert len(prefilter.split_sentences(text)) == 3


@pytest.mark.parametrize(
    "text",
    [
        "Replace it every 2–4 weeks.",
        "clean every 1 - 2 months.",
        "Replace every six(6) months.",
        "Wash the pre-filter every 2–4 weeks to increase efficiency",
    ],
)
def test_typography_does_not_hide_an_interval(text: str) -> None:
    """A real manual writes "2–4", "1 - 2" and "six(6)"; none may be missed."""
    assert prefilter.is_candidate(text) is True
    assert prefilter._has_maintenance_scale(text) is True


def test_an_hours_only_cycle_is_parsed_but_not_scheduled() -> None:
    """The verifier can read "3,000 hours"; the filter does not propose it."""
    parsed = parse_interval("The filter lasts 3,000 hours.")
    assert parsed is not None
    assert parsed.months == pytest.approx(3000 / 720, abs=0.01)
    assert prefilter.is_candidate("The filter lasts 3,000 hours.") is False


def test_the_filter_and_the_verifier_read_the_text_the_same_way() -> None:
    """If the two flattenings drift apart, a found interval cannot be verified."""
    from sloth_drawer.extract.verify import normalise

    samples = [
        "Replace it every 2–4 weeks. Clean every 1 - 2 months.",
        "The filter lasts 3,000 hours (six(6) months).",
        "Wipe the exterior with a dry cloth every 2 weeks.",
    ]
    for sample in samples:
        assert prefilter._flatten(sample) == normalise(sample)


def test_a_wrapped_prose_line_is_rejoined() -> None:
    """ "…every 6" and "months" on separate lines still state an interval."""
    text = "Replace the filter at least every 6\nmonths or when the indicator lights."
    assert prefilter.candidate_sentences(text) != []
