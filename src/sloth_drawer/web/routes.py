"""The HTTP surface: list devices, open a card, log a service.

One page, three routes, zero JavaScript (ARCHITECTURE.md). The card itself at
``/device/{slug}/card`` is the **same** ``render_card`` output
``sloth-drawer card`` writes to ``out/cards/`` — the web UI is a viewer over
the same storage, never a second pipeline, so the demo cannot show something
the CLI would not print.

Configuration arrives as plain paths, not a ``Config``: this package is only
allowed to import ``storage``, ``render`` and ``errors`` (RULES.md 3.1a), so
``cli.py`` — which already owns the config — does the reading.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.exceptions import HTTPException
from starlette.status import HTTP_303_SEE_OTHER

import sloth_drawer.errors as errors
from sloth_drawer.render.card_html import render_card
from sloth_drawer.storage.db import Device, load_devices, open_db
from sloth_drawer.storage.service_log import record_done, schedule_for_device
from sloth_drawer.web import page

NOT_FOUND = 404


def build_router(db_path: Path, devices_toml: Path) -> APIRouter:
    """The routes, bound to the two paths the CLI resolved from its config.

    Each request opens the SQLite database and closes it before returning —
    a read every few seconds cannot justify a process-wide handle against a
    WAL file that a scan may be writing.
    """
    router = APIRouter()

    def _registry() -> tuple[Device, ...]:
        """The registry the devices TOML declares, loaded per request."""
        return load_devices(devices_toml)

    def _row(connection: sqlite3.Connection, slug: str) -> sqlite3.Row:
        """The device's stored row, or a 404 that says what to run first."""
        row = connection.execute("SELECT id FROM devices WHERE slug = ?", (slug,)).fetchone()
        if row is None:
            raise HTTPException(
                status_code=NOT_FOUND,
                detail=f"No scan data for {slug!r} yet. Run <code>sloth-drawer scan</code> first.",
            )
        return row

    def _device(devices: tuple[Device, ...], slug: str) -> Device:
        """The registry entry, or a 404 that names the candidates."""
        for device in devices:
            if device.slug == slug:
                return device
        slugs = ", ".join(device.slug for device in devices)
        raise HTTPException(
            status_code=NOT_FOUND, detail=f"No device {slug!r} in the registry. Known: {slugs}."
        )

    @router.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        """Every device in the registry; scanned ones show their next due date."""
        devices = _registry()
        if not db_path.is_file():
            return HTMLResponse(page.device_list_page([(device, [], False) for device in devices]))
        entries = []
        connection = open_db(db_path)
        try:
            for device in devices:
                row = connection.execute(
                    "SELECT id FROM devices WHERE slug = ?", (device.slug,)
                ).fetchone()
                tasks = schedule_for_device(connection, int(row["id"])) if row else []
                entries.append((device, tasks, row is not None))
        finally:
            connection.close()
        return HTMLResponse(page.device_list_page(entries))

    @router.get("/device/{slug}", response_class=HTMLResponse)
    def show(slug: str, request: Request) -> HTMLResponse:
        """The card's tasks, each with its evidence and a Mark-done form."""
        target = _device(_registry(), slug)
        connection = open_db(db_path)
        try:
            row = _row(connection, slug)
            tasks = schedule_for_device(connection, int(row["id"]))
        finally:
            connection.close()
        flash = (
            "Service logged — the dates below are the new schedule."
            if request.query_params.get("logged")
            else ""
        )
        return HTMLResponse(page.device_page(target, tasks, flash=flash))

    @router.get("/device/{slug}/card", response_class=HTMLResponse)
    def card(slug: str) -> HTMLResponse:
        """The printable card: exactly what ``sloth-drawer card`` renders."""
        target = _device(_registry(), slug)
        connection = open_db(db_path)
        try:
            row = _row(connection, slug)
            tasks = schedule_for_device(connection, int(row["id"]))
        finally:
            connection.close()
        return HTMLResponse(render_card(target, tasks))

    @router.post("/device/{slug}/done")
    def log_done(slug: str, request: Request) -> RedirectResponse:
        """Log a service event, then redirect back with a flash flag.

        The task id travels in the query string, not a form body: FastAPI's
        form parsing would add the ``python-multipart`` dependency for one
        integer, and the redirect-after-post keeps a browser refresh from
        double-logging.
        """
        _device(_registry(), slug)
        interval_id = int(request.query_params.get("interval_id", ""))
        connection = open_db(db_path)
        try:
            _row(connection, slug)
            record_done(
                connection,
                interval_id,
                note=request.query_params.get("note") or None,
            )
        except errors.SlothDrawerError as exc:
            raise HTTPException(status_code=NOT_FOUND, detail=str(exc)) from exc
        finally:
            connection.close()
        return RedirectResponse(
            f"/device/{slug}?logged=1", status_code=HTTP_303_SEE_OTHER
        )

    return router
