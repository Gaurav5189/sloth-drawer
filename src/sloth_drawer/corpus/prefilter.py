"""Deterministic pre-filter: does this text look like it states an interval?

This module is **pure**. It imports nothing from the project except
``errors.py`` and operates on a string, because that is what makes it cheap
enough to run on every chunk of every manual before the model ever sees one
(ARCHITECTURE.md 3).

Two jobs:

*   :func:`score_text` says whether a chunk is worth a model call at all.
*   :func:`candidate_sentences` says *which sentences* inside it look like they
    state an interval.

The second one is how every interval gets found without the model being asked
the same question twice. The code enumerates the candidate sentences and
builds one short excerpt for each; the model is never asked to choose what to
look at next, and it never sees more than one excerpt at a time (C5).

The filter is a blunt instrument on purpose. It is allowed to be wrong in both
directions — a sentence that scores too low is lost, a sentence that scores too
high wastes a model call — because the *verifier*, not the filter, is what
decides whether an interval is real.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: A chunk must reach this score to be worth a model call.
DEFAULT_THRESHOLD = 2

#: A sentence must reach this score to become a candidate.
SENTENCE_THRESHOLD = 2

#: Typographic characters a real manual uses where the pattern expects plain
#: ASCII. "2–4 weeks" and "3,000 hours" are ordinary text; without this the
#: pre-filter would silently miss the intervals they state.
_TRANSLATION = str.maketrans(
    {
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "–": "-",
        "—": "-",
        "‑": "-",
        " ": " ",
        "…": "...",
    }
)

#: A number, written as a digit or spelled out: "6 months", "six(6) months".
_NUMBER = r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
_UNIT = r"(hours?|days?|weeks?|months?|years?)"
#: A manual often writes the number twice: "six(6) months". The parenthetical
#: is optional and never captured, so the group numbers stay stable.
_PAREN = r"(?:\s*\(\s*\d+\s*\))?"

#: An interval a human would actually schedule. A unit of weeks, months or
#: years always counts; a number of days counts once it reaches a week. This
#: keeps a display's "8 hours" and a sensor's "2 days" out of the pipeline
#: without the model ever having to judge what is worth acting on.
_MAINTENANCE_SCALE = re.compile(
    rf"\b{_NUMBER}{_PAREN}\s*(?:-|to|or)?\s*{_NUMBER}?{_PAREN}\s*{_UNIT}\b", re.I
)

#: Sentence end followed by something that starts a new sentence. Deliberately
#: conservative: a table row is not a sentence, and the line break already
#: separates it.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?:;])\s+(?=[A-Z0-9\"'(])")

#: A line that ends like this finishes whatever it was saying.
_ENDS_SENTENCE = re.compile(r"[.!?;:]\s*$")


@dataclass(frozen=True)
class Match:
    """One pattern that fired, and where."""

    name: str
    start: int
    end: int
    text: str


#: (name, pattern, weight). The weight says how strongly the pattern suggests
#: a real maintenance interval, not how often it matches.
_PATTERNS: tuple[tuple[str, re.Pattern[str], int], ...] = (
    (
        "explicit_interval",
        re.compile(
            rf"\bevery\s+{_NUMBER}{_PAREN}\s*(?:-|to|or)\s*{_NUMBER}{_PAREN}\s*{_UNIT}\b", re.I
        ),
        3,
    ),
    (
        "explicit_interval",
        re.compile(rf"\bevery\s+{_NUMBER}{_PAREN}\s*{_UNIT}\b", re.I),
        3,
    ),
    (
        "cycle_expression",
        re.compile(rf"\b{_NUMBER}{_PAREN}\s*(?:-|to|or)\s*{_NUMBER}{_PAREN}\s*{_UNIT}\b", re.I),
        2,
    ),
    (
        "cycle_expression",
        re.compile(rf"\b{_NUMBER}{_PAREN}\s*{_UNIT}\b", re.I),
        1,
    ),
    (
        "whichever_first",
        re.compile(r"\bwhichever\s+(?:comes?\s+)?(?:first|occurs?)\b", re.I),
        2,
    ),
    (
        "filter_life",
        re.compile(r"\bfilter\s+life(?:\s+indicator)?\b", re.I),
        2,
    ),
    (
        "maintenance_task",
        re.compile(
            r"\b(?:replace|clean|descale|wash|rinse|service|inspect|maintain|change|"
            r"maintenance|replacement)\w*",
            re.I,
        ),
        1,
    ),
)


def _flatten(text: str) -> str:
    """Straighten the typography and collapse the whitespace before matching.

    The same normalisation the verifier applies, kept local because this
    module may import nothing from the project (ARCHITECTURE.md 3). If the
    two ever drift apart, an interval the filter finds becomes an interval
    the verifier cannot parse — or a quote the model returns stops matching
    the page. The tests pin them together.
    """
    straightened = text.translate(_TRANSLATION)
    without_thousands = re.sub(r"(?<=\d),(?=\d)", "", straightened)
    # [^\S\n] = whitespace except newline; dash-collapsing must not cross
    # line boundaries because _flat_lines normalises per line.
    without_dash_spaces = re.sub(r"[^\S\n]*-[^\S\n]*", "-", without_thousands)
    return re.sub(r"\s+", " ", without_dash_spaces).strip()


def _to_int(text: str) -> int:
    """A number the manual wrote either as `6` or as `six`."""
    if text.isdigit():
        return int(text)
    word_numbers = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
    }
    return word_numbers[text.lower()]


def score_text(text: str) -> tuple[int, tuple[Match, ...]]:
    """Score a piece of text and return the spans that fired.

    The score is the sum of the weights of the *distinct* patterns that fired,
    so one paragraph repeating "every 3 months" is not worth three times one
    that says it once.
    """
    matches: list[Match] = []
    score = 0
    seen: set[str] = set()
    for name, pattern, weight in _PATTERNS:
        found = list(pattern.finditer(_flatten(text)))
        if not found:
            continue
        if name not in seen:
            score += weight
            seen.add(name)
        for match in found:
            matches.append(
                Match(name=name, start=match.start(), end=match.end(), text=match.group(0))
            )
    return score, tuple(matches)


def is_candidate(text: str, threshold: int = DEFAULT_THRESHOLD) -> bool:
    """Whether a piece of text is worth spending a model call on."""
    score, _ = score_text(text)
    return score >= threshold


def matched_phrases(text: str) -> list[str]:
    """The distinct phrases that fired, for the report and for debugging."""
    _score, matches = score_text(text)
    seen: list[str] = []
    for match in matches:
        if match.name not in seen:
            seen.append(match.name)
    return seen


def split_sentences(text: str) -> list[str]:
    """Split text into sentences.

    PDF extraction hard-wraps prose, so "…every 6" and "months" can land on
    different lines and neither states an interval on its own. Lines are
    therefore re-joined before splitting: a line that does not end a sentence
    continues into the next one when it reads like prose (it is long, or the
    next line starts in lower case). A table row — short, and followed by
    another that starts with a capital — stays its own sentence.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    merged: list[str] = []
    for line in lines:
        if merged:
            previous = merged[-1]
            continues = not _ENDS_SENTENCE.search(previous) and (
                len(previous) >= 60 or line[:1].islower()
            )
            if continues:
                merged[-1] = f"{previous} {line}"
                continue
        merged.append(line)

    sentences: list[str] = []
    for line in merged:
        for part in _SENTENCE_BOUNDARY.split(line):
            part = part.strip()
            if part:
                sentences.append(part)
    return sentences


def _has_maintenance_scale(text: str) -> bool:
    """Whether the text states an interval a person would schedule."""
    for match in _MAINTENANCE_SCALE.finditer(_flatten(text)):
        amount = _to_int(match.group(1))
        unit = match.group(3).lower()
        if not unit.startswith("day"):
            return True
        if amount >= 7:
            return True
    return False


def candidate_sentences(text: str, threshold: int = SENTENCE_THRESHOLD) -> list[str]:
    """The sentences in the text that look like they state an interval.

    The order is preserved and duplicates are dropped, so the same sentence
    appearing twice in one page is only asked about once.
    """
    found: list[str] = []
    seen: set[str] = set()
    for sentence in split_sentences(text):
        score, _ = score_text(sentence)
        if score < threshold or not _has_maintenance_scale(sentence):
            continue
        key = re.sub(r"\s+", " ", sentence).strip().lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(sentence)
    return found
