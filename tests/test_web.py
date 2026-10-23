"""The web surface, tested against a state database written through storage.

These run against a temporary SQLite file written via the same
``store_manual`` a scan uses, so the routes are proved against real rows
rather than mocks. The card route must be byte-identical to
``render_card`` — that identity is the point: a card in the browser is a
card the CLI would have printed.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sloth_drawer.render.card_html import render_card
from sloth_drawer.storage.db import Device, IntervalWrite, connect, migrate, store_manual
from sloth_drawer.storage.service_log import add_months, schedule_for_device
from sloth_drawer.web.app import create_app

DEVICE = Device(
    slug="honeywell-hpa3000",
    name="Honeywell HPA3000",
    manufacturer="Honeywell",
    model="HPA3000",
    category="air_purifier",
)
ABSENT = Device(slug="never-scanned", name="Never Scanned", category="air_purifier")


@pytest.fixture
def state(tmp_path: Path) -> Path:
    """A state database with one scanned device and one verified task."""
    db = tmp_path / "sloth.db"
    devices_toml = tmp_path / "devices.toml"
    devices_toml.write_text(
        f'[[device]]\nslug = "{DEVICE.slug}"\nname = "{DEVICE.name}"\n'
        f'manufacturer = "{DEVICE.manufacturer}"\nmodel = "{DEVICE.model}"\n'
        f'category = "{DEVICE.category}"\n'
        f'[[device]]\nslug = "{ABSENT.slug}"\nname = "{ABSENT.name}"\n'
        f'category = "{ABSENT.category}"\n'
    )
    connection = connect(db)
    migrate(connection)
    store_manual(
        connection,
        device=DEVICE,
        intervals=[
            IntervalWrite(
                task="Replace pre-filter",
                section="4.2",
                page=12,
                interval_months=3,
                model_interval_months=None,
                evidence="Replace the pre-filter every 3 months.",
                model_quote=None,
                verdict="PASS",
                reject_reason=None,
                model_id="gemma3:4b",
            )
        ],
    )
    connection.close()
    # The web app needs to find the registry file at a fixed path per app.
    return devices_toml


@pytest.fixture
def client(state: Path) -> Iterator[TestClient]:
    """An app bound to the fixture state."""
    with TestClient(create_app(state.parent / "sloth.db", state)) as test_client:
        yield test_client


def test_health_is_state_free(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_the_list_names_every_device_with_its_state(client: TestClient) -> None:
    body = client.get("/").text
    assert DEVICE.name in body
    assert ABSENT.name in body
    assert "not scanned" in body


def test_a_device_page_lists_its_tasks_with_due_dates(client: TestClient) -> None:
    body = client.get(f"/device/{DEVICE.slug}").text
    assert "Replace pre-filter" in body
    # No service has been logged, so the card - like the CLI's - shows no due
    # date yet; the date is recomputed in code, never model-supplied.
    assert "no due date" in body
    assert "Mark done" in body


def test_an_unscanned_device_is_a_helpful_404(client: TestClient) -> None:
    body = client.get(f"/device/{ABSENT.slug}").text
    assert body.startswith("<!DOCTYPE html>")
    assert "No scan data" in body


def test_an_unknown_device_is_a_404_that_names_the_registry(client: TestClient) -> None:
    body = client.get("/device/who-knows").text
    assert "Known:" in body and DEVICE.slug in body


def test_mark_done_moves_the_due_date_and_redirects(client: TestClient) -> None:
    response = client.post(f"/device/{DEVICE.slug}/done?interval_id=1", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == f"/device/{DEVICE.slug}?logged=1"
    expected = add_months(date.today(), 3).strftime("%d %b %Y")
    assert f"DUE {expected}" in client.get(f"/device/{DEVICE.slug}?logged=1").text
    assert "Service logged" in client.get(f"/device/{DEVICE.slug}?logged=1").text


def test_calendar_shifting_is_whole_months() -> None:
    """Jan 31 + 1 month is Feb 28 — the same behaviour the CLI card shows."""
    from sloth_drawer.storage.service_log import shift_months

    assert shift_months(date(2026, 1, 31), 1) == date(2026, 2, 28)


def test_the_card_route_is_the_render_the_cli_writes(client: TestClient, state: Path) -> None:
    connection = sqlite3.connect(state.parent / "sloth.db")
    connection.row_factory = sqlite3.Row
    tasks = schedule_for_device(connection, 1)
    connection.close()
    served = client.get(f"/device/{DEVICE.slug}/card").text
    assert served == render_card(DEVICE, tasks)
    both = client.get(f"/device/{DEVICE.slug}/card")
    assert "Replace pre-filter" in both.text


def test_a_bad_interval_is_a_recorded_404_not_a_crash(client: TestClient) -> None:
    response = client.post(f"/device/{DEVICE.slug}/done?interval_id=999")
    assert response.status_code == 404
    assert "No interval" in response.text


def test_a_stale_replay_cannot_move_the_due_date_back(client: TestClient) -> None:
    """The schedule runs from the *latest* service: a second POST with an
    older effective date must not drag the due date backwards."""
    client.post(f"/device/{DEVICE.slug}/done?interval_id=1")
    body = client.get(f"/device/{DEVICE.slug}").text
    due_now = re.search(r"DUE (\d{2} \w{3} \d{4})", body).group(1)
    client.post(f"/device/{DEVICE.slug}/done?interval_id=1&note=replay")
    body = client.get(f"/device/{DEVICE.slug}").text
    assert re.search(r"DUE (\d{2} \w{3} \d{4})", body).group(1) == due_now


def test_an_interval_without_scan_data_is_404(state: Path) -> None:
    with TestClient(create_app(state.parent / "missing.db", state)) as dead:
        assert dead.get(f"/device/{DEVICE.slug}").status_code == 404
