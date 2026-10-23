"""The service log: the one calculation the product rests on.

``next_due = last_done + interval_months`` is computed in code at read time.
These tests pin the calendar arithmetic, the "never recorded" state, and the
fact that a due date changes when the interval changes — none of which a model
is allowed to influence (C1).
"""

from __future__ import annotations

from datetime import date

import pytest

from sloth_drawer.errors import ConfigError, StorageError
from sloth_drawer.storage.db import Device, open_db, upsert_device, upsert_interval
from sloth_drawer.storage.service_log import (
    TaskSchedule,
    add_months,
    format_date,
    last_done,
    next_due,
    parse_date,
    record_done,
    schedule_for_device,
    sort_tasks,
)

EVIDENCE = "The Pre-Carbon filter must be replaced every 2 months."


@pytest.fixture
def connection(tmp_path):
    db = open_db(tmp_path / "sloth.db")
    yield db
    db.close()


def _device(connection, slug: str = "acme-1") -> int:
    return upsert_device(
        connection,
        Device(
            slug=slug,
            name="Acme 1",
            manufacturer="Acme",
            model="A1",
            category="air-purifier",
            manual_path=f"{slug}.pdf",
        ),
    )


def _interval(connection, device_id: int, **overrides) -> int:
    values = {
        "task": "Pre-Carbon filter replacement",
        "section": "4.2 Filter Maintenance",
        "page": 12,
        "interval_months": 2.0,
        "model_interval_months": 2.0,
        "evidence": EVIDENCE,
        "model_quote": "every 2 months",
        "verdict": "PASS",
        "reject_reason": None,
        "model_id": "gemma3:1b",
    }
    values.update(overrides)
    return upsert_interval(connection, device_id, **values)


@pytest.mark.parametrize(
    ("start", "months", "expected"),
    [
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2026, 1, 1), 2, date(2026, 3, 1)),
        (date(2026, 11, 30), 3, date(2027, 2, 28)),
        (date(2026, 1, 1), 12, date(2027, 1, 1)),
    ],
)
def test_whole_months_use_the_calendar(start, months, expected) -> None:
    """A schedule that drifts a few days every month is worse than useless."""
    assert add_months(start, months) == expected


def test_a_fractional_interval_becomes_days() -> None:
    """ "2 weeks" is 0.5 months; half a month is 15 days."""
    assert add_months(date(2026, 1, 1), 0.5) == date(2026, 1, 16)
    assert add_months(date(2026, 1, 1), 0.25) == date(2026, 1, 9)


def test_next_due_without_a_service_date_is_none() -> None:
    """The "never recorded" state. It is a normal state, not an error."""
    assert next_due(None, 2.0) is None
    assert next_due(date(2026, 1, 1), None) is None


def test_dates_round_trip_and_junk_is_refused() -> None:
    assert parse_date("2026-09-14") == date(2026, 9, 14)
    assert parse_date(None) is None
    assert format_date(date(2026, 11, 14)) == "14 Nov 2026"
    assert format_date(None) == ""
    with pytest.raises(ConfigError):
        parse_date("14/09/2026")


def test_re_scanning_is_idempotent(connection) -> None:
    """The conflict keys from ARCHITECTURE.md 5: a device is its slug, an interval
    is (device, task, page). A second scan updates in place, it does not duplicate."""
    device_id = _device(connection)
    first = _interval(connection, device_id)
    second = _interval(connection, device_id, verdict="REPAIR", model_interval_months=3.0)

    assert first == second
    assert connection.execute("SELECT COUNT(*) FROM devices").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM intervals").fetchone()[0] == 1
    assert schedule_for_device(connection, device_id)[0].verdict == "REPAIR"


def test_a_device_is_updated_not_duplicated(connection) -> None:
    device_id = _device(connection)
    again = upsert_device(
        connection,
        Device(slug="acme-1", name="Acme One (renamed)", manual_path="acme-1.pdf"),
    )
    assert again == device_id
    row = connection.execute("SELECT name FROM devices WHERE id = ?", (device_id,)).fetchone()
    assert row["name"] == "Acme One (renamed)"
    assert connection.execute("SELECT COUNT(*) FROM devices").fetchone()[0] == 1


def test_a_logged_service_moves_the_due_date(connection) -> None:
    device_id = _device(connection)
    interval_id = _interval(connection, device_id)

    assert last_done(connection, interval_id) is None
    recorded = record_done(connection, interval_id, done_at=date(2026, 9, 14))
    assert recorded == date(2026, 9, 14)
    assert last_done(connection, interval_id) == date(2026, 9, 14)

    (task,) = schedule_for_device(connection, device_id)
    assert task.next_due == date(2026, 11, 14)
    assert task.ever_serviced is True


def test_the_most_recent_service_wins(connection) -> None:
    device_id = _device(connection)
    interval_id = _interval(connection, device_id)
    record_done(connection, interval_id, done_at=date(2026, 5, 1))
    record_done(connection, interval_id, done_at=date(2026, 9, 14))
    record_done(connection, interval_id, done_at=date(2026, 7, 1))

    assert last_done(connection, interval_id) == date(2026, 9, 14)
    (task,) = schedule_for_device(connection, device_id)
    assert task.next_due == date(2026, 11, 14)


def test_the_due_date_follows_a_changed_interval(connection) -> None:
    """The reason ``next_due`` is not a column: the schedule is derived, not frozen."""
    device_id = _device(connection)
    interval_id = _interval(connection, device_id)
    record_done(connection, interval_id, done_at=date(2026, 1, 1))
    assert schedule_for_device(connection, device_id)[0].next_due == date(2026, 3, 1)

    _interval(connection, device_id, interval_months=6.0)
    assert schedule_for_device(connection, device_id)[0].next_due == date(2026, 7, 1)


def test_logging_a_service_for_an_unknown_interval_is_an_error(connection) -> None:
    with pytest.raises(StorageError):
        record_done(connection, 999)


def test_the_card_shows_the_manufacturers_unit(connection) -> None:
    """The database stores months; the card shows what the manual wrote."""
    device_id = _device(connection)
    _interval(
        connection,
        device_id,
        interval_months=0.5,
        model_interval_months=2.0,
        evidence="The pre-filter should be cleaned every 2 weeks.",
        verdict="REPAIR",
    )
    (task,) = schedule_for_device(connection, device_id)
    assert task.display == "2 weeks"
    assert task.disagreement == "MODEL SAID 2 · SOURCE SAYS 0.5"


def test_a_repaired_task_carries_its_disagreement(connection) -> None:
    device_id = _device(connection)
    _interval(connection, device_id, model_interval_months=3.0, verdict="REPAIR")
    (task,) = schedule_for_device(connection, device_id)
    assert task.verdict == "REPAIR"
    assert task.disagreement == "MODEL SAID 3 · SOURCE SAYS 2"


def test_a_passed_task_has_no_disagreement(connection) -> None:
    device_id = _device(connection)
    _interval(connection, device_id)
    (task,) = schedule_for_device(connection, device_id)
    assert task.disagreement is None


def test_a_rejected_interval_is_returned_but_never_accepted(connection) -> None:
    device_id = _device(connection)
    _interval(
        connection,
        device_id,
        task="",
        interval_months=None,
        model_interval_months=None,
        evidence=None,
        verdict="REJECT",
        reject_reason="no_interval_in_citation",
    )
    (task,) = schedule_for_device(connection, device_id)
    assert task.accepted is False
    assert task.next_due is None
    assert task.display == "—"


def _task(name: str, *, due: date | None, months: float = 2.0, verdict: str = "PASS"):
    return TaskSchedule(
        interval_id=abs(hash(name)) % 1000,
        task=name,
        section=None,
        page=1,
        verdict=verdict,
        reject_reason=None,
        evidence=None,
        interval_months=months,
        model_interval_months=months,
        display=f"{months:g} months",
        last_done=None,
        next_due=due,
    )


def test_the_hero_is_the_soonest_due() -> None:
    later = _task("HEPA filter replacement", due=date(2027, 1, 1), months=12.0)
    sooner = _task("Pre-filter cleaning", due=date(2026, 11, 1), months=2.0)
    ordered = sort_tasks([later, sooner])
    assert [task.task for task in ordered] == ["Pre-filter cleaning", "HEPA filter replacement"]


def test_a_never_serviced_task_sorts_after_a_dated_one() -> None:
    """A task with no service history has no due date, so it cannot be "sooner"."""
    undated = _task("Pre-filter cleaning", due=None, months=2.0)
    dated = _task("HEPA filter replacement", due=date(2027, 6, 1), months=12.0)
    ordered = sort_tasks([undated, dated])
    assert [task.task for task in ordered] == ["HEPA filter replacement", "Pre-filter cleaning"]


def test_undated_tasks_are_ordered_by_interval() -> None:
    long_interval = _task("HEPA filter replacement", due=None, months=12.0)
    short_interval = _task("Pre-filter cleaning", due=None, months=2.0)
    ordered = sort_tasks([long_interval, short_interval])
    assert [task.task for task in ordered] == ["Pre-filter cleaning", "HEPA filter replacement"]


def test_a_rejected_task_never_becomes_the_hero() -> None:
    rejected = _task("unknown", due=date(2026, 1, 1), months=1.0, verdict="REJECT")
    accepted = _task("Pre-filter cleaning", due=date(2027, 1, 1), months=2.0)
    ordered = sort_tasks([rejected, accepted])
    assert ordered[0].task == "Pre-filter cleaning"
