"""The local database: schema, migrations, and the device registry.

Stdlib ``sqlite3`` only (RULES.md 1.1). Two properties matter:

*   **Re-scanning is idempotent.** Every write is an ``INSERT ... ON CONFLICT
    DO UPDATE``, so running ``scan`` twice leaves the same rows, not duplicates.
    The conflict keys come from ``ARCHITECTURE.md`` 5 — a device is its slug, an
    interval is ``(device, task, page)``.
*   **The database holds no fact the model produced.** ``interval_months`` is
    written from the verifier's number, and ``model_interval_months`` keeps the
    model's claim beside it for the report. A wrong model output cannot change
    a schedule (C1).

The device registry (``data/devices.toml``) is read here too, with stdlib
``tomllib``: it is hand-edited local state, and the model never invents a device
(C10).
"""

from __future__ import annotations

import sqlite3
import tomllib
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from sloth_drawer.errors import ConfigError, StorageError

#: Numbered migrations, applied in order and recorded in ``PRAGMA user_version``.
#: Never edit a migration that has shipped — append a new one.
MIGRATIONS: tuple[str, ...] = (
    # 1 — the schema from ARCHITECTURE.md 5.
    """
    CREATE TABLE devices (
      id            INTEGER PRIMARY KEY,
      slug          TEXT UNIQUE NOT NULL,
      name          TEXT NOT NULL,
      manufacturer  TEXT,
      model         TEXT,
      category      TEXT,
      manual_path   TEXT,
      created_at    TEXT NOT NULL
    );

    CREATE TABLE intervals (
      id                     INTEGER PRIMARY KEY,
      device_id              INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
      task                   TEXT NOT NULL,
      section                TEXT,
      page                   INTEGER,
      interval_months        REAL,
      model_interval_months  REAL,
      evidence               TEXT,
      model_quote            TEXT,
      verdict                TEXT NOT NULL,
      reject_reason          TEXT,
      model_id               TEXT NOT NULL,
      prompt_hash            TEXT,
      created_at             TEXT NOT NULL,
      UNIQUE(device_id, task, page)
    );

    CREATE TABLE service_events (
      id           INTEGER PRIMARY KEY,
      interval_id  INTEGER NOT NULL REFERENCES intervals(id) ON DELETE CASCADE,
      done_at      TEXT NOT NULL,
      note         TEXT
    );

    CREATE TABLE runs (
      id            INTEGER PRIMARY KEY,
      started_at    TEXT NOT NULL,
      finished_at   TEXT,
      model_id      TEXT,
      backend       TEXT,
      manuals       INTEGER,
      chunks        INTEGER,
      candidates    INTEGER,
      found         INTEGER,
      passed        INTEGER,
      repaired      INTEGER,
      rejected      INTEGER,
      seconds       REAL,
      tokens        INTEGER,
      cost_usd      REAL DEFAULT 0
    );

    CREATE INDEX intervals_device_idx ON intervals(device_id);
    CREATE INDEX service_events_interval_idx ON service_events(interval_id, done_at);
    """,
)

#: The schema version this module expects.
SCHEMA_VERSION = len(MIGRATIONS)


@dataclass(frozen=True)
class Device:
    """One row of the registry: a physical thing and the manual that describes it."""

    slug: str
    name: str
    manufacturer: str | None = None
    model: str | None = None
    category: str | None = None
    manual_path: str | None = None

    @property
    def subtitle(self) -> str:
        """``Manufacturer · model``, skipping whichever half is missing."""
        parts = [part for part in (self.manufacturer, self.model) if part]
        return " · ".join(parts)


@dataclass(frozen=True)
class IntervalRow:
    """A stored interval, exactly as the verifier left it."""

    id: int
    device_id: int
    task: str
    section: str | None
    page: int | None
    interval_months: float | None
    model_interval_months: float | None
    evidence: str | None
    model_quote: str | None
    verdict: str
    reject_reason: str | None
    model_id: str

    @property
    def accepted(self) -> bool:
        return self.verdict in ("PASS", "REPAIR")


@dataclass(frozen=True)
class RunRecord:
    """One scan, summarised. This is the row the report reads back."""

    started_at: str
    finished_at: str | None
    model_id: str
    backend: str
    manuals: int
    chunks: int
    candidates: int
    found: int
    passed: int
    repaired: int
    rejected: int
    seconds: float
    tokens: int
    cost_usd: float = 0.0


def now_iso() -> str:
    """The current time, UTC, second precision — the format every row stores."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def connect(path: Path) -> sqlite3.Connection:
    """Open (and create) the database, with the pragmas this project needs.

    WAL keeps a reader — the web UI or a second ``card`` invocation — from
    blocking a scan. ``foreign_keys`` is off by default in SQLite and must be
    turned on per connection.
    """
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(path))
    except (sqlite3.Error, OSError) as exc:
        raise StorageError(f"Could not open the database at {path}: {exc}") from exc

    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA synchronous = NORMAL")
    except sqlite3.Error as exc:
        connection.close()
        raise StorageError(f"Could not configure the database at {path}: {exc}") from exc
    return connection


def migrate(connection: sqlite3.Connection) -> int:
    """Apply every migration the database has not seen. Returns the new version."""
    try:
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        for index in range(version, len(MIGRATIONS)):
            connection.executescript(MIGRATIONS[index])
            connection.execute(f"PRAGMA user_version = {index + 1}")
        connection.commit()
    except sqlite3.Error as exc:
        connection.rollback()
        raise StorageError(f"The database migration failed: {exc}") from exc
    return max(version, len(MIGRATIONS))


def open_db(path: Path) -> sqlite3.Connection:
    """Open the database and bring it up to the current schema."""
    connection = connect(path)
    migrate(connection)
    return connection


def load_devices(path: Path) -> tuple[Device, ...]:
    """Read ``data/devices.toml``.

    A missing or malformed registry is a configuration error: without it the
    tool cannot say which physical thing a manual belongs to, and the card has
    no name to print.
    """
    path = Path(path)
    if not path.is_file():
        raise ConfigError(
            f"Device registry not found: {path}. "
            f"Create it with one [[device]] block per manual (see README.md)."
        )
    try:
        with path.open("rb") as handle:
            payload = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"Could not read {path}: {exc}") from exc

    entries = payload.get("device")
    if not isinstance(entries, list) or not entries:
        raise ConfigError(f"{path} defines no [[device]] entries.")

    devices: list[Device] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise ConfigError(f"{path}: device #{index} is not a table.")
        slug = str(entry.get("slug") or "").strip()
        name = str(entry.get("name") or "").strip()
        if not slug or not name:
            raise ConfigError(f"{path}: device #{index} needs both a slug and a name.")
        if slug in seen:
            raise ConfigError(f"{path}: the slug {slug!r} is used twice.")
        seen.add(slug)
        devices.append(
            Device(
                slug=slug,
                name=name,
                manufacturer=_optional(entry.get("manufacturer")),
                model=_optional(entry.get("model")),
                category=_optional(entry.get("category")),
                manual_path=_optional(entry.get("manual")),
            )
        )
    return tuple(devices)


def _optional(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def manual_index(devices: tuple[Device, ...]) -> dict[str, str]:
    """Map a manual filename to its device slug, for the scan."""
    return {device.manual_path: device.slug for device in devices if device.manual_path is not None}


def upsert_device(connection: sqlite3.Connection, device: Device, *, commit: bool = True) -> int:
    """Insert or refresh a device, and return its row id.

    ``commit=False`` leaves the write inside the caller's open transaction, so a
    batch can commit one manual's device and intervals together (RULES.md 2.6).
    """
    try:
        cursor = connection.execute(
            "INSERT INTO devices ("
            "  slug, name, manufacturer, model, category, manual_path, created_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(slug) DO UPDATE SET "
            "  name = excluded.name, manufacturer = excluded.manufacturer, "
            "  model = excluded.model, category = excluded.category, "
            "  manual_path = excluded.manual_path "
            "RETURNING id",
            (
                device.slug,
                device.name,
                device.manufacturer,
                device.model,
                device.category,
                device.manual_path,
                now_iso(),
            ),
        )
        row = cursor.fetchone()
        if commit:
            connection.commit()
    except sqlite3.Error as exc:
        if commit:
            connection.rollback()
        raise StorageError(f"Could not store the device {device.slug!r}: {exc}") from exc
    if row is None:
        raise StorageError(f"Could not store the device {device.slug!r}.")
    return int(row[0])


def upsert_interval(
    connection: sqlite3.Connection,
    device_id: int,
    *,
    task: str,
    section: str | None,
    page: int | None,
    interval_months: float | None,
    model_interval_months: float | None,
    evidence: str | None,
    model_quote: str | None,
    verdict: str,
    reject_reason: str | None,
    model_id: str,
    prompt_hash: str | None = None,
    commit: bool = True,
) -> int:
    """Insert or refresh one interval. Re-scanning the same manual changes nothing.

    ``commit=False`` keeps the write inside the caller's transaction; see
    :func:`store_manual`.
    """
    try:
        cursor = connection.execute(
            "INSERT INTO intervals ("
            "  device_id, task, section, page, interval_months, model_interval_months, "
            "  evidence, model_quote, verdict, reject_reason, model_id, prompt_hash, created_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(device_id, task, page) DO UPDATE SET "
            "  section = excluded.section, interval_months = excluded.interval_months, "
            "  model_interval_months = excluded.model_interval_months, "
            "  evidence = excluded.evidence, model_quote = excluded.model_quote, "
            "  verdict = excluded.verdict, reject_reason = excluded.reject_reason, "
            "  model_id = excluded.model_id, prompt_hash = excluded.prompt_hash "
            "RETURNING id",
            (
                device_id,
                task,
                section,
                page,
                interval_months,
                model_interval_months,
                evidence,
                model_quote,
                verdict,
                reject_reason,
                model_id,
                prompt_hash,
                now_iso(),
            ),
        )
        row = cursor.fetchone()
        if commit:
            connection.commit()
    except sqlite3.Error as exc:
        if commit:
            connection.rollback()
        raise StorageError(f"Could not store an interval for device {device_id}: {exc}") from exc
    if row is None:
        raise StorageError(f"Could not store an interval for device {device_id}.")
    return int(row[0])


@dataclass(frozen=True)
class IntervalWrite:
    """One interval ready to store, exactly as the verifier left it."""

    task: str
    section: str | None
    page: int | None
    interval_months: float | None
    model_interval_months: float | None
    evidence: str | None
    model_quote: str | None
    verdict: str
    reject_reason: str | None
    model_id: str
    prompt_hash: str | None = None


def store_manual(
    connection: sqlite3.Connection,
    device: Device,
    intervals: Sequence[IntervalWrite],
) -> int:
    """Write one manual's device row and intervals in a single transaction.

    This is the batch runner's unit of durability (RULES.md 2.6): either the
    whole manual lands, or none of it does, so a crash mid-corpus leaves the
    previous manual committed and the current one absent. Returns the device id.
    """
    try:
        with connection:  # commits on success, rolls back on any exception
            device_id = upsert_device(connection, device, commit=False)
            for interval in intervals:
                upsert_interval(connection, device_id, commit=False, **asdict(interval))
    except sqlite3.Error as exc:
        raise StorageError(
            f"Could not store the manual {device.slug!r} in one transaction: {exc}"
        ) from exc
    return device_id


def record_run(connection: sqlite3.Connection, run: RunRecord) -> int:
    """Append one scan summary."""
    try:
        cursor = connection.execute(
            "INSERT INTO runs ("
            "  started_at, finished_at, model_id, backend, manuals, chunks, candidates, "
            "  found, passed, repaired, rejected, seconds, tokens, cost_usd"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run.started_at,
                run.finished_at,
                run.model_id,
                run.backend,
                run.manuals,
                run.chunks,
                run.candidates,
                run.found,
                run.passed,
                run.repaired,
                run.rejected,
                run.seconds,
                run.tokens,
                run.cost_usd,
            ),
        )
        connection.commit()
    except sqlite3.Error as exc:
        connection.rollback()
        raise StorageError(f"Could not record the run: {exc}") from exc
    return int(cursor.lastrowid or 0)


def find_device(connection: sqlite3.Connection, slug: str) -> sqlite3.Row | None:
    """Look a device up by its slug."""
    return connection.execute("SELECT * FROM devices WHERE slug = ?", (slug,)).fetchone()


def intervals_for_device(connection: sqlite3.Connection, device_id: int) -> list[IntervalRow]:
    """Every interval stored for a device, accepted or not."""
    rows = connection.execute(
        "SELECT id, device_id, task, section, page, interval_months, model_interval_months, "
        "       evidence, model_quote, verdict, reject_reason, model_id "
        "FROM intervals WHERE device_id = ? ORDER BY task, page",
        (device_id,),
    ).fetchall()
    return [
        IntervalRow(
            id=int(row["id"]),
            device_id=int(row["device_id"]),
            task=str(row["task"]),
            section=row["section"],
            page=int(row["page"]) if row["page"] is not None else None,
            interval_months=_as_float(row["interval_months"]),
            model_interval_months=_as_float(row["model_interval_months"]),
            evidence=row["evidence"],
            model_quote=row["model_quote"],
            verdict=str(row["verdict"]),
            reject_reason=row["reject_reason"],
            model_id=str(row["model_id"]),
        )
        for row in rows
    ]


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)  # type: ignore[arg-type]
