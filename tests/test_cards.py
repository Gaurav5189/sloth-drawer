"""The card: the tangible artifact.

Three things are non-negotiable and therefore tested:

*   the card is a **single file with no network reference** — no ``<script>``,
    no ``@font-face``, no URL;
*   the terminal card is **exactly 80 columns**, in Unicode and in ``--ascii``;
*   a device whose manual yielded nothing still gets a card that says so — a
    blank card is a bug (DESIGN.md 5.1).
"""

from __future__ import annotations

import re

import pytest

from sloth_drawer.render import render_card_html, render_card_text
from sloth_drawer.render.card_html import hero_label, split_display
from sloth_drawer.render.card_text import WIDTH
from sloth_drawer.storage.db import Device, open_db, upsert_device, upsert_interval
from sloth_drawer.storage.service_log import schedule_for_device

EVIDENCE = "The Pre-Carbon filter (Part No. DX-CF14) must be replaced every 2 months."


@pytest.fixture
def connection(tmp_path):
    db = open_db(tmp_path / "sloth.db")
    yield db
    db.close()


def _device(connection, **overrides) -> Device:
    values = {
        "slug": "duramax-dx900p",
        "name": "DuraMax 900 Series Air Purifier",
        "manufacturer": "DuraMax",
        "model": "DX-900P",
        "category": "air-purifier",
        "manual_path": "duramax-dx900p.pdf",
    }
    values.update(overrides)
    device = Device(**values)
    upsert_device(connection, device)
    return device


def _interval(connection, slug: str, **overrides) -> None:
    row = connection.execute("SELECT id FROM devices WHERE slug = ?", (slug,)).fetchone()
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
    upsert_interval(connection, int(row["id"]), **values)


def _tasks(connection, slug: str):
    row = connection.execute("SELECT id FROM devices WHERE slug = ?", (slug,)).fetchone()
    return schedule_for_device(connection, int(row["id"]))


@pytest.mark.parametrize(
    ("task", "expected"),
    [
        ("Pre-Carbon filter replacement", "REPLACE EVERY"),
        ("Particle Sensor Cleaning", "CLEAN EVERY"),
        ("Filter cleaning cycle", "CLEAN EVERY"),
        ("Washable pre-filter rinse", "WASH EVERY"),
        ("Replace Every 3 months", "REPLACE EVERY"),
        ("Task", "REPLACE EVERY"),
    ],
)
def test_the_hero_label_comes_from_the_task_verb(task, expected) -> None:
    assert hero_label(task) == expected


@pytest.mark.parametrize(
    ("display", "expected"),
    [("2 months", ("2", "months")), ("2 weeks", ("2", "weeks")), ("3-6 months", ("3-6", "months"))],
)
def test_the_hero_number_and_unit_are_split(display, expected) -> None:
    assert split_display(display) == expected


def test_the_html_card_carries_the_whole_artifact(connection) -> None:
    device = _device(connection)
    _interval(connection, device.slug)
    html = render_card_html(device, _tasks(connection, device.slug))

    assert html.startswith("<!DOCTYPE html>")
    assert 'lang="en"' in html
    assert "DuraMax 900 Series Air Purifier" in html
    assert "DuraMax · DX-900P" in html
    assert "REPLACE EVERY" in html
    assert '<span class="hero-number">2</span>' in html
    assert "Pre-Carbon filter replacement" in html
    assert EVIDENCE in html
    assert "MANUAL p.12 · 4.2 FILTER MAINTENANCE" in html
    assert "VERIFIED" in html


def test_the_html_card_never_touches_the_network(connection) -> None:
    """A local-first tool that downloads a typeface is a joke about itself."""
    device = _device(connection)
    _interval(connection, device.slug)
    html = render_card_html(device, _tasks(connection, device.slug))

    assert "<script" not in html.lower()
    assert "@font-face" not in html
    assert "http://" not in html
    assert "https://" not in html
    assert "url(" not in html


def test_a_repair_prints_the_disagreement(connection) -> None:
    device = _device(connection)
    _interval(connection, device.slug, model_interval_months=3.0, verdict="REPAIR")
    html = render_card_html(device, _tasks(connection, device.slug))
    assert "MODEL SAID 3 · SOURCE SAYS 2" in html
    assert "CORRECTED" in html


def test_a_never_serviced_device_says_so(connection) -> None:
    device = _device(connection)
    _interval(connection, device.slug)
    html = render_card_html(device, _tasks(connection, device.slug))
    assert "no service recorded" in html


def test_a_serviced_device_shows_the_due_date(connection) -> None:
    device = _device(connection)
    _interval(connection, device.slug)
    task = _tasks(connection, device.slug)[0]
    connection.execute(
        "INSERT INTO service_events (interval_id, done_at, note) VALUES (?, ?, ?)",
        (task.interval_id, "2026-09-14", None),
    )
    connection.commit()
    html = render_card_html(device, _tasks(connection, device.slug))
    assert "14 Nov 2026" in html


def test_a_device_with_nothing_verified_still_gets_a_card(connection) -> None:
    device = _device(connection)
    _interval(
        connection,
        device.slug,
        task="",
        interval_months=None,
        model_interval_months=None,
        evidence=None,
        verdict="REJECT",
        reject_reason="no_interval_in_citation",
    )
    html = render_card_html(device, _tasks(connection, device.slug))
    assert "INTERVAL NOT FOUND" in html
    assert "Searched pages 12" in html

    text = render_card_text(device, _tasks(connection, device.slug), color=False)
    assert "INTERVAL NOT FOUND" in text


def test_the_card_escapes_the_device_name(connection) -> None:
    device = _device(connection, name='<script>alert("x")</script>', model="A&B")
    _interval(connection, device.slug)
    html = render_card_html(device, _tasks(connection, device.slug))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "A&amp;B" in html


def test_the_terminal_card_is_exactly_80_columns(connection) -> None:
    device = _device(connection)
    _interval(connection, device.slug)
    text = render_card_text(device, _tasks(connection, device.slug), color=False)
    for line in text.splitlines():
        assert len(line) == WIDTH, f"{len(line)} columns: {line!r}"


def test_the_ascii_card_is_exactly_80_columns_and_pure_ascii(connection) -> None:
    device = _device(connection)
    _interval(
        connection,
        device.slug,
        task="Washable AOC™ Carbon Filter — cleaning",
        evidence=(
            "Washable AOC™ Carbon Filter • Clean once every 3 months — Lasts ≈12 months. "
            "When the Check Filter Indicator LED is on, it is time to replace the True HEPA "
            "Filter and the Washable AOC™ Carbon Filter together."
        ),
    )
    text = render_card_text(device, _tasks(connection, device.slug), color=False, ascii_only=True)
    lines = text.splitlines()
    for line in lines:
        assert len(line) == WIDTH, f"{len(line)} columns: {line!r}"
        assert line.isascii(), f"non-ASCII in an --ascii card: {line!r}"
    assert "+-" in text
    assert "[x] VERIFIED" in text
    assert "(TM)" in text

    # An ASCII expansion (™ -> (TM)) must not push the evidence box past its own
    # border: a card whose right edge is eaten by an ellipsis is a broken card.
    boxed = [line for line in lines if line.startswith("| | ")]
    assert boxed, "the evidence box disappeared"
    for line in boxed:
        assert line.endswith("| |"), line


def test_a_long_device_name_is_truncated_in_the_terminal_only(connection) -> None:
    name = "Extremely Long Manufacturer Name Air Purifier With A Very Long Model Name Indeed"
    device = _device(connection, name=name)
    _interval(connection, device.slug)
    text = render_card_text(device, _tasks(connection, device.slug), color=False)
    assert "…" in text
    assert name in render_card_html(device, _tasks(connection, device.slug))


def test_colour_is_opt_in(connection) -> None:
    device = _device(connection)
    _interval(connection, device.slug)
    plain = render_card_text(device, _tasks(connection, device.slug), color=False)
    coloured = render_card_text(device, _tasks(connection, device.slug), color=True)
    assert "\x1b[" not in plain
    assert "\x1b[" in coloured
    assert re.sub(r"\x1b\[[0-9;]*m", "", coloured) == plain


def test_the_evidence_wraps_and_is_never_truncated(connection) -> None:
    device = _device(connection)
    _interval(connection, device.slug, evidence=EVIDENCE)
    text = render_card_text(device, _tasks(connection, device.slug), color=False)
    body = text.replace("\n", " ")
    for word in ("Pre-Carbon", "DX-CF14", "2 months"):
        assert word in body
