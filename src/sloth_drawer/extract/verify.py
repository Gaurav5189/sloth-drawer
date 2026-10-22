"""THE VERIFIER.

The model may point at a sentence. It may not assert a fact. This module is
where that distinction is enforced, and it is deliberately the dullest,
most paranoid code in the project.

The four failure modes it exists to catch:

*   **The quote is not in the page.** The model invented it. → REJECT
*   **The cited sentence states no interval.** The model pointed at something
    that looks like a maintenance instruction but is not one — "Do not wash
    the Pre-Carbon filter." → REJECT
*   **The model's number is wrong.** The sentence says 2 months, the model
    said 3. → REPAIR: the code's number wins and the disagreement is recorded.
*   **The model's task name is invented.** → REJECT

Everything here is a pure function over text. This module imports nothing from
the project except ``errors.py``, which is what makes it testable without a
model — and therefore testable enough to be the headline of the project
(ARCHITECTURE.md 3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sloth_drawer.errors import VerificationError

#: Verdict statuses.
PASS = "PASS"
REPAIR = "REPAIR"
REJECT = "REJECT"
SKIP = "SKIP"

#: Rejection reason codes. These are stable: they go in the report and in the
#: post, and a reader must be able to look one up.
EMPTY_QUOTE = "empty_quote"
QUOTE_NOT_IN_PAGE = "quote_not_in_page"
NO_INTERVAL_IN_CITATION = "no_interval_in_citation"
TASK_NOT_IN_SOURCE = "task_not_in_source"

#: Skip reason codes.
NO_INTERVAL_STATED = "no_interval_stated"

#: How long a quoted sentence may be before it stops being a sentence and
#: becomes a table. Beyond this the surrounding text is used instead.
MAX_SENTENCE_CHARS = 400

#: How much context to keep around a quote when the quote sits in a table.
WINDOW_CHARS = 200

#: Two intervals are "the same" when they differ by less than this many
#: months. Below it, the difference is float noise, not a disagreement.
TOLERANCE = 0.01

#: Months per unit. These are the same conversions the prompt states, so a
#: model that follows the rules is never "repaired" for nothing.
MONTHS_PER_UNIT: dict[str, float] = {
    "hour": 1 / 720,
    "day": 1 / 30,
    "week": 1 / 4,
    "month": 1.0,
    "year": 12.0,
}

#: Words that carry no information about *which* task a sentence is about.
#: A task made only of these cannot be checked, so it is not rejected.
_GENERIC_TASK_WORDS = frozenset(
    {
        "replace",
        "replacement",
        "clean",
        "cleaning",
        "filter",
        "filters",
        "service",
        "maintenance",
        "maintain",
        "check",
        "inspect",
        "inspection",
        "descale",
        "wash",
        "rinse",
        "part",
        "unit",
        "the",
        "and",
        "for",
        "your",
        "this",
        "that",
        "with",
    }
)

#: Typographic characters that must not decide whether a quote matches, and
#: thousands separators that must not break a number. "2–4 weeks" and "3,000
#: hours" are ordinary text in a real manual.
_TRANSLATION = str.maketrans(
    {
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "–": "-",
        "—": "-",
        "‑": "-",
        " ": " ",
        "…": "...",
    }
)

#: Numbers a manual spells out: "every six(6) months".
_WORD_NUMBERS: dict[str, int] = {
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

_NUMBER = r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
_UNIT = r"(hours?|days?|weeks?|months?|years?)"
#: A manual often writes the number twice: "six(6) months". The parenthetical
#: is optional and never captured, so the group numbers stay stable.
_PAREN = r"(?:\s*\(\s*\d+\s*\))?"
_RANGE = re.compile(
    rf"\b{_NUMBER}{_PAREN}\s*(?:-|to|or)\s*{_NUMBER}{_PAREN}\s*{_UNIT}\b", re.IGNORECASE
)
_SINGLE = re.compile(rf"\b{_NUMBER}{_PAREN}\s*{_UNIT}\b", re.IGNORECASE)

#: A sentence ends at a terminator followed by a new sentence — not at the
#: full stop inside "Part No. DX-CF14". The lookbehinds skip the abbreviations
#: a manual is full of; each one is fixed-width, which ``re`` requires.
_TERMINATOR = re.compile(
    r"(?<![Nn]o)(?<![Ff]ig)(?<![Ss]ec)(?<![Pp]t)(?<![Ss]td)(?<![Aa]pprox)"
    r"(?<![Ii]nc)(?<!etc\.)"
    r"[.!?]\s+(?=[A-Z0-9\"'(])"
)


@dataclass(frozen=True)
class Interval:
    """An interval as the manual states it, and as the code computes it.

    ``value`` and ``unit`` are what the card shows — the manufacturer's own
    number in the manufacturer's own unit, because "2 weeks" is what the
    manual says and "0.5 months" is not. ``months`` is what the schedule is
    computed from.
    """

    value: float | str
    unit: str
    months: float
    raw: str

    @property
    def display(self) -> str:
        """How the interval reads on a card: the manufacturer's own unit."""
        if isinstance(self.value, str):
            return f"{self.value} {self.unit}"
        amount = float(self.value)
        shown = f"{amount:g}"
        unit = self.unit
        if amount == 1 and unit.endswith("s"):
            unit = unit[:-1]
        return f"{shown} {unit}"


@dataclass(frozen=True)
class Verdict:
    """What the verifier decided about one model answer."""

    status: str
    reason: str | None = None
    interval_months: float | None = None
    model_interval_months: float | None = None
    interval: Interval | None = None
    evidence: str | None = None
    model_quote: str | None = None
    page: int = 1
    section: str | None = None
    notes: tuple[str, ...] = ()

    @property
    def accepted(self) -> bool:
        """Whether this verdict may become a card entry."""
        return self.status in (PASS, REPAIR)

    @property
    def disagreement(self) -> str | None:
        """The footnote a REPAIR prints on the card."""
        if self.status != REPAIR:
            return None
        model = self.model_interval_months
        code = self.interval_months
        model_text = f"{model:g}" if isinstance(model, (int, float)) else str(model)
        code_text = f"{code:g}" if isinstance(code, (int, float)) else str(code)
        return f"MODEL SAID {model_text} · SOURCE SAYS {code_text}"


def normalise(text: str) -> str:
    """Flatten whitespace, straighten quotes, unite dashes, drop digit commas.

    Two texts that differ only in how the PDF wrapped them, in which curly
    quote the manufacturer used, in whether the interval was "2–4 weeks" or
    "2-4 weeks", or in whether the dash had spaces around it, are the same
    text. Everything else is left alone, because this is what decides whether
    a quote is verbatim.
    """
    straightened = text.translate(_TRANSLATION)
    without_thousands = re.sub(r"(?<=\d),(?=\d)", "", straightened)
    # [^\S\n] = whitespace except newline; dash-collapsing must not cross
    # line boundaries because _flat_lines normalises per line.
    without_dash_spaces = re.sub(r"[^\S\n]*-[^\S\n]*", "-", without_thousands)
    return re.sub(r"\s+", " ", without_dash_spaces).strip()


def _to_int(text: str) -> int:
    """A number the manual wrote either as `6` or as `six`."""
    return int(text) if text.isdigit() else _WORD_NUMBERS[text.lower()]


_TERMINATOR = re.compile(
    r"(?<![Nn]o)(?<![Ff]ig)(?<![Ss]ec)(?<![Pp]t)(?<![Ss]td)(?<![Aa]pprox)"
    r"(?<![Ii]nc)(?<!etc\.)"
    r"[.!?]\s+(?=[A-Z0-9\"'(])"
)


def _unit_key(unit: str) -> str:
    return unit.rstrip("s").lower()


def parse_interval(text: str) -> Interval | None:
    """Find an interval in a piece of text.

    Ranges are read as their midpoint, which is the same rule the prompt
    states, so the model and the code agree.
    """
    flat = normalise(text)
    if not flat:
        return None

    ranges = list(_RANGE.finditer(flat))
    singles = list(_SINGLE.finditer(flat))
    if not ranges and not singles:
        return None

    if ranges:
        match = ranges[0]
        low = _to_int(match.group(1))
        high = _to_int(match.group(2))
        unit = match.group(3).lower()
        months = (low + high) / 2 * MONTHS_PER_UNIT[_unit_key(unit)]
        return Interval(
            value=f"{low}-{high}", unit=unit, months=round(months, 2), raw=match.group(0)
        )

    match = singles[0]
    amount = _to_int(match.group(1))
    unit = match.group(2).lower()
    months = amount * MONTHS_PER_UNIT[_unit_key(unit)]
    return Interval(value=amount, unit=unit, months=round(months, 2), raw=match.group(0))


def _interval_matches(text: str) -> list[tuple[int, Interval]]:
    """Every interval in the text, with its offset."""
    found: list[tuple[int, Interval]] = []
    for match in _RANGE.finditer(text):
        low = _to_int(match.group(1))
        high = _to_int(match.group(2))
        unit = match.group(3).lower()
        months = (low + high) / 2 * MONTHS_PER_UNIT[_unit_key(unit)]
        found.append(
            (match.start(), Interval(f"{low}-{high}", unit, round(months, 2), match.group(0)))
        )
    for match in _SINGLE.finditer(text):
        amount = _to_int(match.group(1))
        unit = match.group(2).lower()
        months = amount * MONTHS_PER_UNIT[_unit_key(unit)]
        found.append((match.start(), Interval(amount, unit, round(months, 2), match.group(0))))
    return found


def locate_quote(page_text: str, quote: str) -> tuple[int, int, int] | None:
    """Find the quote in the page.

    Returns ``(start, end, occurrences)`` in the flattened page text, or
    ``None`` when the quote is not there. The occurrence count is how the
    verifier notices a page that says the same thing twice.
    """
    flat_page = normalise(page_text)
    flat_quote = normalise(quote)
    if not flat_quote:
        return None

    pattern = re.compile(re.escape(flat_quote), re.IGNORECASE)
    found = pattern.search(flat_page)
    if found is None:
        stripped = flat_quote.rstrip(" .,:;")
        if not stripped:
            return None
        pattern = re.compile(re.escape(stripped), re.IGNORECASE)
        found = pattern.search(flat_page)
        if found is None:
            return None

    return found.start(), found.end(), len(pattern.findall(flat_page))


def _flat_lines(page_text: str) -> tuple[str, list[tuple[int, int, str]]]:
    """Flatten a page for matching, while remembering where its lines are.

    Returns the flattened text (one space between tokens, no newlines) and,
    for every source line, its ``(start, end, text)`` span in that flat text.
    The spans are what let the expansion stop at a heading instead of running
    back to the title on the first page.
    """
    flat_parts: list[str] = []
    spans: list[tuple[int, int, str]] = []
    cursor = 0
    for raw in page_text.splitlines():
        # The same normalisation as :func:`normalise`, applied per line, so the
        # offsets this function returns line up with the ones locate_quote
        # returns. If the two ever drift, a verified quote points at the wrong
        # sentence — the tests pin them together.
        line = normalise(raw)
        if not line:
            continue
        if flat_parts:
            flat_parts.append(" ")
            cursor += 1
        spans.append((cursor, cursor + len(line), line))
        flat_parts.append(line)
        cursor += len(line)
    return "".join(flat_parts), spans


#: A line this short that does not end a sentence is a heading or a table row,
#: not the middle of a paragraph. Lines of body text in a manual run long.
_BOUNDARY_LINE_CHARS = 72


def expand_to_sentence(page_text: str, start: int, end: int) -> tuple[str, int]:
    """Grow the quote to the sentence that contains it.

    Takes the **original** page text — with its line breaks — because a line
    break is half of what a sentence boundary is. Returns the sentence and its
    start offset in the flattened page, so the caller can tell which interval
    inside it the quote was pointing at.

    The quote the model returns is often useless on its own — "every 2 months"
    — so the sentence around it is what carries the interval. Two things keep
    the expansion honest: a full stop only ends a sentence when something that
    can start one follows it (so "Part No. DX-CF14" does not cut a sentence in
    half), and a line that is too short to be body text is treated as a
    boundary (so the expansion does not run back through a heading to the
    title of the manual).

    When the sentence still runs past the length a sentence should have, the
    quote sits in a table: a window around the quote is used instead.
    """
    flat, spans = _flat_lines(page_text)
    if not spans:
        return page_text[start : min(len(page_text), end + 1)].strip(), start

    flat_length = len(flat)

    def ends_sentence(line: str) -> bool:
        return bool(_TERMINATOR.search(line + " X"))

    index = next(
        (i for i, (s, e, _line) in enumerate(spans) if s <= start < e),
        len(spans) - 1,
    )
    last = next(
        (i for i, (s, e, _line) in enumerate(spans) if s < end <= e),
        index,
    )

    first_line = index
    while first_line > 0:
        previous = spans[first_line - 1][2]
        if ends_sentence(previous) or len(previous) < _BOUNDARY_LINE_CHARS:
            break
        first_line -= 1
    end_line = last
    while end_line < len(spans) - 1:
        current = spans[end_line][2]
        if ends_sentence(current):
            break
        end_line += 1

    sentence_start = spans[first_line][0]
    sentence_end = spans[end_line][1]

    if sentence_end - sentence_start > MAX_SENTENCE_CHARS:
        sentence_start = max(0, start - WINDOW_CHARS)
        sentence_end = min(flat_length, end + WINDOW_CHARS)

    return flat[sentence_start:sentence_end].strip(), sentence_start


def _task_is_grounded(task: str, source: str) -> bool:
    """Whether the task name comes from the cited sentence (C10).

    The distinctive words of the task — the ones that are not generic
    maintenance vocabulary — must appear in the sentence the model pointed at.
    Checking against the sentence rather than the page is what catches a model
    that names the wrong filter: a card that said "HEPA filter" over evidence
    about the Pre-Carbon filter would be a wrong card, and the interval on it
    would be trusted.

    A task made only of generic words cannot be checked, so it is not
    rejected; it merely makes for a vague card.
    """
    distinctive = [
        word
        for word in re.findall(r"[a-z0-9]+", task.lower())
        if len(word) >= 3 and word not in _GENERIC_TASK_WORDS
    ]
    if not distinctive:
        return True
    haystack = normalise(source).lower()
    return any(word in haystack for word in distinctive)


def verify(
    model_output: dict,
    page_text: str,
    *,
    page: int = 1,
    section: str | None = None,
) -> Verdict:
    """Decide what a model answer is worth.

    ``model_output`` is the parsed JSON the model returned. ``page_text`` is
    the text of the page the model claims the quote came from.
    """
    if not isinstance(model_output, dict):
        raise VerificationError("The model output was not a JSON object.")

    quote = str(model_output.get("quote") or "").strip()
    task = str(model_output.get("task") or "").strip()
    section = section or (str(model_output.get("section") or "").strip() or None)

    if model_output.get("has_interval") is False:
        return Verdict(
            status=SKIP,
            reason=NO_INTERVAL_STATED,
            model_quote=quote or None,
            page=page,
            section=section,
        )

    raw_model_months = model_output.get("interval_months")
    model_months: float | None = None
    if isinstance(raw_model_months, (int, float)) and not isinstance(raw_model_months, bool):
        model_months = float(raw_model_months)

    if not quote:
        return Verdict(
            status=REJECT,
            reason=EMPTY_QUOTE,
            model_interval_months=model_months,
            model_quote=None,
            page=page,
            section=section,
        )

    located = locate_quote(page_text, quote)
    if located is None:
        return Verdict(
            status=REJECT,
            reason=QUOTE_NOT_IN_PAGE,
            model_interval_months=model_months,
            model_quote=quote,
            page=page,
            section=section,
        )
    start, end, occurrences = located

    sentence, sentence_start = expand_to_sentence(page_text, start, end)

    matches = _interval_matches(sentence)
    if not matches:
        return Verdict(
            status=REJECT,
            reason=NO_INTERVAL_IN_CITATION,
            model_interval_months=model_months,
            model_quote=quote,
            page=page,
            section=section,
            notes=("ambiguous_quote",) if occurrences > 1 else (),
        )

    # The interval the code trusts is the one closest to the quote the model
    # pointed at. A table with three filters yields three intervals, and the
    # model pointed at one of them.
    quote_offset = start - sentence_start
    best = min(matches, key=lambda item: abs(item[0] - quote_offset))
    interval = best[1]

    if task and not _task_is_grounded(task, sentence):
        return Verdict(
            status=REJECT,
            reason=TASK_NOT_IN_SOURCE,
            model_interval_months=model_months,
            interval=interval,
            evidence=sentence,
            model_quote=quote,
            page=page,
            section=section,
        )

    notes: tuple[str, ...] = ("ambiguous_quote",) if occurrences > 1 else ()
    code_months = interval.months

    if model_months is None or abs(model_months - code_months) > TOLERANCE:
        return Verdict(
            status=REPAIR,
            reason=None,
            interval_months=code_months,
            model_interval_months=model_months,
            interval=interval,
            evidence=sentence,
            model_quote=quote,
            page=page,
            section=section,
            notes=notes,
        )

    return Verdict(
        status=PASS,
        reason=None,
        interval_months=code_months,
        model_interval_months=model_months,
        interval=interval,
        evidence=sentence,
        model_quote=quote,
        page=page,
        section=section,
        notes=notes,
    )
