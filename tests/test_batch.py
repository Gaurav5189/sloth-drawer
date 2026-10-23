"""The batch runner and the one-row-per-key write policy.

``intervals`` is unique on ``(device_id, task, page)`` (RULES.md 2.6), but
candidates are not unique on it: two excerpts of one chunk can name the same
task, and a failed extraction is stored under the task name ``""``. The row
holds exactly one of them, and which one it holds must not be decided by scan
order — a REJECT landing after a PASS would replace a verified interval, so the
report would count the PASS while no card could show it.

These tests also pin the two batch properties the phase exists for: one
transaction per manual, and a checkpoint that lets ``--resume`` skip an
unchanged manual that is already done.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import sloth_drawer.batch as batch
import sloth_drawer.storage.db as db
from sloth_drawer.batch import (
    CHECKPOINT_NAME,
    Checkpoint,
    ManualOutcome,
    run_batch,
    store_scan,
    winner_rows,
)
from sloth_drawer.config import Config, Paths
from sloth_drawer.corpus.ingest import Manual, NoTextLayerError, Page
from sloth_drawer.errors import ConfigError, StorageError
from sloth_drawer.extract.verify import Verdict
from sloth_drawer.pipeline import Candidate, ManualScan
from sloth_drawer.storage.db import Device, open_db

EVIDENCE = "The Pre-Carbon filter (Part No. DX-CF14) must be replaced every 2 months."

DEVICE = Device(
    slug="duramax-dx900p",
    name="DuraMax 900 Series Air Purifier",
    manufacturer="DuraMax",
    model="DX-900P",
    category="air-purifier",
    manual_path="duramax-dx900p.pdf",
)


@pytest.fixture
def config(tmp_path) -> Config:
    """A resolvable config whose every output lands under ``tmp_path``."""
    return Config(
        paths=Paths(root=tmp_path),
        ollama_host="http://127.0.0.1:11434",
        ollama_timeout=30.0,
        retrieval="local",
        database_url=None,
        embed_model="nomic-embed-text",
        embed_dims=768,
        sentry_dsn=None,
    )


def _accepted(
    task: str, page: int, *, status: str, months: float, model_months: float
) -> Candidate:
    return _candidate(
        task,
        page,
        Verdict(
            status=status,
            interval_months=months,
            model_interval_months=model_months,
            evidence=EVIDENCE,
        ),
    )


def _rejected(task: str, page: int, reason: str) -> Candidate:
    return _candidate(task, page, Verdict(status="REJECT", reason=reason))


def _candidate(task: str, page: int, verdict: Verdict) -> Candidate:
    return Candidate(
        manual_slug=DEVICE.slug,
        manual_path=DEVICE.manual_path,
        page=page,
        section="4.2 Filter Maintenance",
        excerpt=EVIDENCE,
        task=task,
        quote="every 2 months",
        verdict=verdict,
        model_id="gemma3:1b",
    )


def _store(config: Config, *candidates: Candidate) -> list[tuple[str, str]]:
    """Write candidates via ``store_scan`` and read the rows back as ``(task, verdict)``."""
    connection = open_db(config.paths.db)
    try:
        store_scan(connection, DEVICE, list(candidates), model="gemma3:1b")
        rows = connection.execute("SELECT task, verdict FROM intervals ORDER BY task").fetchall()
    finally:
        connection.close()
    return [(str(row["task"]), str(row["verdict"])) for row in rows]


def test_a_reject_does_not_take_the_row_of_a_verified_interval(config) -> None:
    """The failure CodeRabbit flagged: the REJECT is second, and must lose."""
    rows = _store(
        config,
        _accepted("Pre-Carbon filter replacement", 12, status="PASS", months=2.0, model_months=2.0),
        _rejected("Pre-Carbon filter replacement", 12, "quote_not_in_page"),
    )
    assert rows == [("Pre-Carbon filter replacement", "PASS")]


def test_the_row_keeps_the_answer_the_source_agreed_with(config) -> None:
    """The shape the corpus produced: one key, a PASS and a REPAIR."""
    rows = _store(
        config,
        _accepted("Clean once every 3 months", 1, status="PASS", months=3.0, model_months=3.0),
        _accepted("Clean once every 3 months", 1, status="REPAIR", months=12.0, model_months=3.0),
    )
    assert rows == [("Clean once every 3 months", "PASS")]


def test_two_candidates_that_agree_still_keep_the_last_one(config) -> None:
    rows = _store(
        config,
        _accepted("Replace filters", 12, status="PASS", months=6.0, model_months=6.0),
        _accepted("Replace filters", 12, status="PASS", months=12.0, model_months=12.0),
    )
    assert rows == [("Replace filters", "PASS")]


def test_distinct_keys_are_separate_rows_and_skips_are_not_stored(config) -> None:
    """The dedup is by (task, page) only — it must not over-merge."""
    skipped = _candidate(
        "Clean the pre-filter", 12, Verdict(status="SKIP", reason="no_interval_stated")
    )
    rows = _store(
        config,
        _accepted("Pre-Carbon filter replacement", 12, status="PASS", months=2.0, model_months=2.0),
        _accepted("Pre-Carbon filter replacement", 14, status="PASS", months=2.0, model_months=2.0),
        _accepted("Replace the HEPA filter", 12, status="PASS", months=12.0, model_months=12.0),
        skipped,
    )
    assert rows == [
        ("Pre-Carbon filter replacement", "PASS"),
        ("Pre-Carbon filter replacement", "PASS"),
        ("Replace the HEPA filter", "PASS"),
    ]


def test_winner_rows_records_the_model_disagreement() -> None:
    """A REPAIR keeps the model's number beside the code's, for the report."""
    rows = winner_rows(
        [_accepted("Replace filters", 12, status="REPAIR", months=6.0, model_months=3.0)],
        DEVICE.slug,
        model="gemma3:1b",
    )
    assert len(rows) == 1
    assert rows[0].interval_months == 6.0
    assert rows[0].model_interval_months == 3.0
    assert rows[0].verdict == "REPAIR"


def test_a_manual_is_written_in_one_transaction(config, monkeypatch) -> None:
    """If the second interval fails, the first must not survive either."""
    connection = open_db(config.paths.db)
    real = db.upsert_interval
    seen = {"count": 0}

    def flaky(conn, device_id, **kwargs):
        seen["count"] += 1
        if seen["count"] == 2:
            raise StorageError("simulated failure on the second interval")
        return real(conn, device_id, **kwargs)

    monkeypatch.setattr(db, "upsert_interval", flaky)
    with pytest.raises(StorageError):
        store_scan(
            connection,
            DEVICE,
            [
                _accepted("Replace filters", 12, status="PASS", months=6.0, model_months=6.0),
                _accepted(
                    "Replace the HEPA filter", 13, status="PASS", months=12.0, model_months=12.0
                ),
            ],
            model="gemma3:1b",
        )
    connection.close()

    reopened = open_db(config.paths.db)
    try:
        assert reopened.execute("SELECT COUNT(*) FROM intervals").fetchone()[0] == 0
        assert reopened.execute("SELECT COUNT(*) FROM devices").fetchone()[0] == 0
    finally:
        reopened.close()


def _write_pdf(directory: Path, name: str, payload: bytes = b"%PDF-1.4 not really") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(payload)
    return path


def test_the_checkpoint_round_trips_through_disk(config) -> None:
    path = config.paths.out / CHECKPOINT_NAME
    checkpoint = Checkpoint(
        started_at="2026-10-25T08:00:00+00:00",
        updated_at="2026-10-25T08:01:00+00:00",
        model_id="gemma3:1b",
        backend="local",
        outcomes={
            "a.pdf": ManualOutcome(
                manual="a.pdf",
                slug="a",
                sha256="a" * 64,
                status="done",
                candidates=3,
                passed=2,
                repaired=1,
                rejection_reasons={"quote_not_in_page": 1},
            )
        },
    )
    checkpoint.save(path)
    loaded = Checkpoint.load(path)
    assert loaded is not None
    assert loaded.model_id == "gemma3:1b"
    assert loaded.outcomes["a.pdf"].passed == 2
    assert loaded.outcomes["a.pdf"].rejection_reasons == {"quote_not_in_page": 1}


def test_a_corrupt_checkpoint_is_an_error_not_a_silent_restart(config) -> None:
    path = config.paths.out / CHECKPOINT_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(StorageError, match="Delete it to start fresh"):
        Checkpoint.load(path)


def test_resume_skips_an_unchanged_manual(config, tmp_path, monkeypatch) -> None:
    manuals = tmp_path / "manuals"
    path = _write_pdf(manuals, "duramax-dx900p.pdf")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()

    checkpoint = Checkpoint(
        started_at="2026-10-25T08:00:00+00:00",
        updated_at="2026-10-25T08:00:00+00:00",
        model_id="gemma3:1b",
        backend="local",
        outcomes={
            path.name: ManualOutcome(
                manual=path.name,
                slug=DEVICE.slug,
                sha256=sha,
                status="done",
                candidates=2,
                passed=1,
                repaired=1,
                chunks=4,
                seconds=41.0,
                tokens=900,
            )
        },
    )
    checkpoint.save(config.paths.out / CHECKPOINT_NAME)

    def explode(*_args, **_kwargs):  # pragma: no cover - must never be reached
        raise AssertionError("a resumed manual must not be scanned again")

    monkeypatch.setattr(batch, "scan_manual", explode)
    monkeypatch.setattr(batch, "read_manual", explode)

    seen: list[str] = []
    outcome = run_batch(
        manuals,
        config=config,
        devices=(DEVICE,),
        model="gemma3:1b",
        resume=True,
        persist=False,
        progress=lambda event: seen.append(event.status),
    )

    assert outcome.resumed == 1
    assert outcome.processed == 0
    assert seen == ["resumed"]
    assert outcome.candidates == ()  # `--list` therefore needs its resumed note
    assert outcome.report.manuals == 1
    assert outcome.report.found == 2
    assert outcome.report.seconds == 41.0


def test_resume_refuses_a_checkpoint_from_a_different_model(config, tmp_path) -> None:
    manuals = tmp_path / "manuals"
    _write_pdf(manuals, "duramax-dx900p.pdf")
    Checkpoint(
        started_at="t",
        updated_at="t",
        model_id="phi4-mini:latest",
        backend="local",
    ).save(config.paths.out / CHECKPOINT_NAME)

    with pytest.raises(ConfigError, match="--force"):
        run_batch(manuals, config=config, model="gemma3:1b", resume=True, persist=False)


def test_an_unreadable_manual_is_recorded(config, tmp_path, monkeypatch) -> None:
    manuals = tmp_path / "manuals"
    _write_pdf(manuals, "scanned.pdf")

    def no_text(path, _slug):
        raise NoTextLayerError(f"{path.name} has no text layer")

    monkeypatch.setattr(batch, "read_manual", no_text)
    outcome = run_batch(manuals, config=config, model="gemma3:1b", persist=False)

    assert outcome.processed == 1
    assert outcome.outcomes[0].status == "skipped"
    assert outcome.outcomes[0].reason == "no_text_layer"
    assert outcome.report.skipped_manuals == 1
    assert outcome.report.skipped_files[0].reason == "no_text_layer"


def test_an_unreadable_manual_still_registers_its_device(config, tmp_path, monkeypatch) -> None:
    """A broken manual must still produce an "interval not found" card, not an error."""
    manuals = tmp_path / "manuals"
    _write_pdf(manuals, DEVICE.manual_path)

    def no_text(_path, _slug):
        raise NoTextLayerError("no text layer")

    monkeypatch.setattr(batch, "read_manual", no_text)
    outcome = run_batch(manuals, config=config, devices=(DEVICE,), model="gemma3:1b")

    assert outcome.report.skipped_manuals == 1
    connection = open_db(config.paths.db)
    try:
        row = connection.execute("SELECT id FROM devices WHERE slug = ?", (DEVICE.slug,)).fetchone()
    finally:
        connection.close()
    assert row is not None


def test_a_processed_manual_is_persisted_in_one_transaction_and_reported(
    config, tmp_path, monkeypatch
) -> None:
    manuals = tmp_path / "manuals"
    _write_pdf(manuals, DEVICE.manual_path)

    def fake_read(path, slug):
        return Manual(
            slug=slug,
            path=Path(path),
            sha256="f" * 64,
            pages=(Page(number=12, text=EVIDENCE, source=path.name),),
        )

    def fake_scan(_manual, **_kwargs):
        return ManualScan(
            candidates=[
                _accepted(
                    "Pre-Carbon filter replacement",
                    12,
                    status="PASS",
                    months=2.0,
                    model_months=2.0,
                ),
                _rejected("Pre-Carbon filter replacement", 12, "quote_not_in_page"),
            ],
            chunks=1,
        )

    monkeypatch.setattr(batch, "read_manual", fake_read)
    monkeypatch.setattr(batch, "scan_manual", fake_scan)

    outcome = run_batch(manuals, config=config, devices=(DEVICE,), model="gemma3:1b")

    assert outcome.report.manuals == 1
    assert outcome.report.passed == 1
    assert outcome.report.rejected == 1
    assert config.paths.report_json.is_file()

    connection = open_db(config.paths.db)
    try:
        rows = connection.execute("SELECT task, verdict FROM intervals").fetchall()
    finally:
        connection.close()
    # The REJECT and the PASS shared (task, page); only the PASS may remain.
    assert [(row["task"], row["verdict"]) for row in rows] == [
        ("Pre-Carbon filter replacement", "PASS")
    ]
