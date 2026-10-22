"""Tests for the verifier — the part of the project worth most tests.

Every case here is one of the failure modes the verifier exists to catch, or
one of the awkward shapes a real manual throws at it: a quote that spans a
line wrap, a quote with curly quotes in it, a quote that is the whole page, a
sentence that appears twice.
"""

from __future__ import annotations

import pytest

from sloth_drawer.extract.verify import (
    EMPTY_QUOTE,
    NO_INTERVAL_IN_CITATION,
    NO_INTERVAL_STATED,
    PASS,
    QUOTE_NOT_IN_PAGE,
    REJECT,
    REPAIR,
    SKIP,
    TASK_NOT_IN_SOURCE,
    expand_to_sentence,
    locate_quote,
    parse_interval,
    verify,
)

PAGE = """DuraMax 900 Series Air Purifier -- User Manual (Model DX-900P)

Section 4.2 Filter Maintenance
The Pre-Carbon filter (Part No. DX-CF14) must be replaced every 2 months.
Replace the Pre-Carbon filter sooner if the FILTER LIFE indicator flashes
red or after 720 hours of continuous operation, whichever occurs first.
Note: Do not wash the Pre-Carbon filter. Washing it will damage the carbon
layer and reduce filtration performance.
The HEPA filter (Part No. DX-HF22) should be replaced every 12 months.
The carbon filter (Part No. DX-CF30) should be replaced every 3 months.

Section 4.3 Exterior Care
Wipe the exterior with a dry cloth every 2 weeks. Do not use solvents.
Replace the Pre-Motor filter (Part No. DX-PF07) every 90 days."""


def _output(**overrides) -> dict:
    base = {
        "has_interval": True,
        "task": "Pre-Carbon filter replacement",
        "interval_months": 2,
        "quote": "The Pre-Carbon filter (Part No. DX-CF14) must be replaced every 2 months.",
        "section": "4.2 Filter Maintenance",
    }
    base.update(overrides)
    return base


# --- the four rejection reasons -------------------------------------------------


def test_a_hallucinated_quote_is_rejected() -> None:
    verdict = verify(_output(quote="The Pre-Carbon filter must be replaced every 6 months."), PAGE)
    assert verdict.status == REJECT
    assert verdict.reason == QUOTE_NOT_IN_PAGE


def test_a_citation_with_no_interval_is_rejected() -> None:
    verdict = verify(
        _output(interval_months=9, quote="Note: Do not wash the Pre-Carbon filter."),
        PAGE,
    )
    assert verdict.status == REJECT
    assert verdict.reason == NO_INTERVAL_IN_CITATION


def test_an_empty_quote_is_rejected() -> None:
    verdict = verify(_output(quote=""), PAGE)
    assert verdict.status == REJECT
    assert verdict.reason == EMPTY_QUOTE


def test_an_invented_task_is_rejected() -> None:
    verdict = verify(
        _output(task="HEPA cartridge replacement", quote="every 2 months"),
        PAGE,
    )
    assert verdict.status == REJECT
    assert verdict.reason == TASK_NOT_IN_SOURCE


# --- the repair path ------------------------------------------------------------


def test_a_wrong_number_is_repaired_in_favour_of_the_code() -> None:
    verdict = verify(_output(interval_months=3), PAGE)
    assert verdict.status == REPAIR
    assert verdict.interval_months == 2
    assert verdict.model_interval_months == 3
    assert verdict.disagreement == "MODEL SAID 3 · SOURCE SAYS 2"


def test_a_zero_interval_is_repaired_not_accepted() -> None:
    verdict = verify(_output(interval_months=0), PAGE)
    assert verdict.status == REPAIR
    assert verdict.interval_months == 2


# --- the pass path --------------------------------------------------------------


def test_a_correct_answer_passes() -> None:
    verdict = verify(_output(), PAGE)
    assert verdict.status == PASS
    assert verdict.interval_months == 2
    assert verdict.interval is not None
    assert verdict.interval.display == "2 months"


def test_a_quote_fragment_is_expanded_to_its_sentence() -> None:
    """The model often returns a useless fragment; the code finds the sentence."""
    verdict = verify(_output(quote="every 2 months"), PAGE)
    assert verdict.status == PASS
    assert verdict.evidence is not None
    assert "must be replaced every 2 months" in verdict.evidence


def test_has_interval_false_is_a_skip_not_a_failure() -> None:
    verdict = verify(_output(has_interval=False, interval_months=0, quote=""), PAGE)
    assert verdict.status == SKIP
    assert verdict.reason == NO_INTERVAL_STATED


# --- the awkward shapes ---------------------------------------------------------


def test_a_quote_that_spans_a_line_wrap_still_matches() -> None:
    wrapped = (
        "The Pre-Carbon filter (Part No. DX-CF14) must be\n"
        "replaced every 2 months.\n"
        "Nothing else on this page matters."
    )
    verdict = verify(_output(quote="must be replaced every 2 months"), wrapped)
    assert verdict.status == PASS
    assert verdict.interval_months == 2


def test_a_quote_with_curly_quotes_still_matches() -> None:
    curly = "The Pre-Carbon filter “must be replaced every 2 months.”"
    verdict = verify(_output(quote="must be replaced every 2 months."), curly)
    assert verdict.status == PASS


def test_a_quote_that_is_the_whole_page_is_found() -> None:
    verdict = verify(_output(quote=PAGE.strip()), PAGE)
    # The page has several intervals, so the closest one to the quote wins.
    assert verdict.status in (PASS, REPAIR)
    assert verdict.interval_months is not None


def test_a_sentence_that_appears_twice_takes_the_first_and_notes_it() -> None:
    doubled = f"{PAGE}\n\nThe Pre-Carbon filter (Part No. DX-CF14) must be replaced every 2 months."
    verdict = verify(_output(), doubled)
    assert verdict.status == PASS
    assert "ambiguous_quote" in verdict.notes


def test_a_table_row_is_measured_from_the_row_the_model_pointed_at() -> None:
    table = (
        "Filter replacement table\n"
        "Pre-Carbon filter 6 months Replacement\n"
        "HEPA filter 12 months Replacement\n"
        "Carbon filter 3 months Replacement"
    )
    verdict = verify(
        _output(
            interval_months=3, quote="Carbon filter 3 months Replacement", task="Carbon filter"
        ),
        table,
    )
    assert verdict.status == PASS
    assert verdict.interval_months == 3


# --- the parser -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "months", "display"),
    [
        ("replace it every 2 months", 2, "2 months"),
        ("replace it every 12 months", 12, "12 months"),
        ("replace it every 1 year", 12, "1 year"),
        ("replace it every 90 days", 3, "90 days"),
        ("replace it every 2 weeks", 0.5, "2 weeks"),
        ("replace it every 14 days", 0.47, "14 days"),
        ("replace it every 3-6 months", 4.5, "3-6 months"),
        ("filter life 12 months", 12, "12 months"),
    ],
)
def test_the_code_uses_the_same_conversions_the_prompt_states(
    text: str, months: float, display: str
) -> None:
    parsed = parse_interval(text)
    assert parsed is not None
    assert parsed.months == pytest.approx(months)
    assert parsed.display == display


def test_text_with_no_interval_parses_to_nothing() -> None:
    assert parse_interval("Do not wash the filter.") is None


def test_the_expansion_stops_at_a_sentence_boundary() -> None:
    start, end, _occurrences = locate_quote(PAGE, "every 2 months")  # type: ignore[misc]
    sentence, _offset = expand_to_sentence(PAGE, start, end)  # type: ignore[arg-type]
    assert "2 months" in sentence
    assert len(sentence) < 400


def test_the_expansion_is_not_fooled_by_an_abbreviation() -> None:
    start, end, _occurrences = locate_quote(PAGE, "must be replaced every 2 months")  # type: ignore[misc]
    sentence, _offset = expand_to_sentence(PAGE, start, end)  # type: ignore[arg-type]
    assert sentence.startswith("The Pre-Carbon filter (Part No. DX-CF14)")


def test_the_expansion_stops_at_a_heading() -> None:
    start, end, _occurrences = locate_quote(PAGE, "every 90 days")  # type: ignore[misc]
    sentence, _offset = expand_to_sentence(PAGE, start, end)  # type: ignore[arg-type]
    assert sentence.startswith("Replace the Pre-Motor filter")
    assert "User Manual" not in sentence


def test_a_verdict_knows_whether_it_may_reach_a_card() -> None:
    assert verify(_output(), PAGE).accepted is True
    assert verify(_output(interval_months=3), PAGE).accepted is True
    assert verify(_output(quote="nothing like this"), PAGE).accepted is False
