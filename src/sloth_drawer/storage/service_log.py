"""The service log, and the one calculation the whole product rests on.

``next_due = last_done + interval_months``, computed **at read time, by code**.
It is not a column, and no model ever touches it. That is deliberate on two
counts (ARCHITECTURE.md 5):

*   a wrong model output can only ever produce a *missing* card, never a wrong
    date (C1);
*   changing an interval retroactively changes the schedule, because the date
    was never frozen into the row.

The card's interval is re-read from the verified evidence sentence rather than
stored separately, so the manufacturer's own unit ("2 weeks") survives even
though the database keeps the scheduling value in months.
"""

from __future__ import annotations

import calendar
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

from sloth_drawer.errors import ConfigError, StorageError
from sloth_drawer.extract.verify import parse_interval

#: Average days in a month, used only for the fractional part of an interval
#: ("2 weeks" is 0.5 months → 15 days). Whole months use the calendar, so
#: "2 months" from 1 Jan is 1 Mar, not 2 Mar.
DAYS_PER_MONTH = 30.4375

#: How a due date reads on a card: "14 Nov 2026".
DATE_FORMAT = "%d %b %Y"


@dataclass(frozen=True)
class TaskSchedule:
    """One task on a card: what it is, when it is next due, and what proves it."""

    interval_id: int
    task: str
    section: str | None
    page: int | None
    verdict: str
    reject_reason: str | None
    evidence: str | None
    interval_months: float | None
    model_interval_months: float | None
    display: str
    last_done: date | None = None
    next_due: date | None = None

    @property
    def accepted(self) -> bool:
        """Whether this task may appear on a card as a fact."""
        return self.verdict in ("PASS", "REPAIR")

    @property
    def ever_serviced(self) -> bool:
        return self.last_done is not None

    @property
    def disagreement(self) -> str | None:
        """The footnote a REPAIR prints: the model's number beside the source's."""
        if self.verdict != "REPAIR":
            return None
        model = _number(self.model_interval_months)
        code = _number(self.interval_months)
        return f"MODEL SAID {model} · SOURCE SAYS {code}"


def _number(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:g}"


def parse_date(value: str | date | None) -> date | None:
    """Read an ISO date. ``None`` stays ``None``; junk is a configuration error."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ConfigError(f"{value!r} is not a date in YYYY-MM-DD form.") from exc


def format_date(value: date | None) -> str:
    """How a date reads on a card. An empty string when there is no date."""
    return value.strftime(DATE_FORMAT) if value else ""


def shift_months(start: date, months: int) -> date:
    """Add whole calendar months, clamping the day to the target month.

    "31 Jan + 1 month" is 28 Feb, not 3 Mar. A schedule that drifts by a few
    days every month is worse than useless.
    """
    total = start.month - 1 + months
    year = start.year + total // 12
    month = total % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def add_months(start: date, months: float) -> date:
    """Add a possibly fractional number of months to a date."""
    whole = int(months)
    remainder = months - whole
    shifted = shift_months(start, whole)
    return shifted + timedelta(days=round(remainder * DAYS_PER_MONTH))


def next_due(last_done: date | None, interval_months: float | None) -> date | None:
    """The one calculation. ``None`` when the device has never been serviced."""
    if last_done is None or interval_months is None:
        return None
    return add_months(last_done, interval_months)


def record_done(
    connection: sqlite3.Connection,
    interval_id: int,
    *,
    done_at: date | None = None,
    note: str | None = None,
) -> date:
    """Log that a task was done. Returns the date that was recorded."""
    recorded = done_at or date.today()
    exists = connection.execute("SELECT 1 FROM intervals WHERE id = ?", (interval_id,)).fetchone()
    if exists is None:
        raise StorageError(f"No interval with id {interval_id}.")
    try:
        connection.execute(
            "INSERT INTO service_events (interval_id, done_at, note) VALUES (?, ?, ?)",
            (interval_id, recorded.isoformat(), note),
        )
        connection.commit()
    except sqlite3.Error as exc:
        connection.rollback()
        raise StorageError(f"Could not record the service event: {exc}") from exc
    return recorded


def last_done(connection: sqlite3.Connection, interval_id: int) -> date | None:
    """The most recent date this task was logged, or ``None`` if never."""
    row = connection.execute(
        "SELECT MAX(done_at) AS done_at FROM service_events WHERE interval_id = ?",
        (interval_id,),
    ).fetchone()
    if row is None or row["done_at"] is None:
        return None
    return parse_date(str(row["done_at"]))


def schedule_for_device(connection: sqlite3.Connection, device_id: int) -> list[TaskSchedule]:
    """Every task for a device, with its last-done date and its next-due date.

    Rejected candidates are returned too: a card must be able to say "this
    manual states no verifiable interval" rather than print nothing.
    """
    rows = connection.execute(
        "SELECT id, task, section, page, interval_months, model_interval_months, "
        "       evidence, verdict, reject_reason "
        "FROM intervals WHERE device_id = ? ORDER BY task, page",
        (device_id,),
    ).fetchall()

    schedules: list[TaskSchedule] = []
    for row in rows:
        interval_id = int(row["id"])
        evidence = row["evidence"]
        months = _as_float(row["interval_months"])
        done = last_done(connection, interval_id)
        schedules.append(
            TaskSchedule(
                interval_id=interval_id,
                task=str(row["task"]),
                section=row["section"],
                page=int(row["page"]) if row["page"] is not None else None,
                verdict=str(row["verdict"]),
                reject_reason=row["reject_reason"],
                evidence=evidence,
                interval_months=months,
                model_interval_months=_as_float(row["model_interval_months"]),
                display=_display(evidence, months),
                last_done=done,
                next_due=next_due(done, months),
            )
        )
    return schedules


def sort_tasks(tasks: list[TaskSchedule]) -> list[TaskSchedule]:
    """Order tasks for the card: the hero first.

    The hero is the soonest due — recency is what a sloth can act on. A task
    that has never been logged has no due date, so it sorts after every dated
    task and is ordered by how short its interval is.
    """
    return sorted(
        tasks,
        key=lambda task: (
            not task.accepted,
            task.next_due is None,
            task.next_due or date.max,
            task.interval_months if task.interval_months is not None else float("inf"),
            task.task,
        ),
    )


def _display(evidence: str | None, months: float | None) -> str:
    """The interval in the manufacturer's own unit, recovered from the evidence.

    The database stores months because that is what a schedule needs. The card
    must show "2 weeks" when the manual said "2 weeks", so the verified sentence
    is re-parsed — by code, at read time, never by a model.
    """
    if evidence:
        interval = parse_interval(evidence)
        if interval is not None:
            return interval.display
    if months is None:
        return "—"
    unit = "month" if months == 1 else "months"
    return f"{months:g} {unit}"


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)  # type: ignore[arg-type]
