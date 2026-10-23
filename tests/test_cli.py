"""What the scan writes when two candidates share one row's key.

``intervals`` is unique on ``(device_id, task, page)`` (RULES.md 2.6), but
candidates are not unique on it: two excerpts of one chunk can name the same
task, and a failed extraction is stored under the task name ``""``. The row
holds exactly one of them, and which one it holds must not be decided by scan
order — a REJECT landing after a PASS would replace a verified interval, so the
report would count the PASS while no card could show it.
"""

from __future__ import annotations

import pytest

from sloth_drawer.cli import _persist
from sloth_drawer.config import Config, Paths
from sloth_drawer.extract.verify import Verdict
from sloth_drawer.pipeline import Candidate, ScanResult
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


def _persist_candidates(config: Config, *candidates: Candidate) -> list[tuple[str, str]]:
    """Write the candidates and read the rows back as ``(task, verdict)``."""
    result = ScanResult(candidates=list(candidates))
    _persist(result, (DEVICE,), config, model="gemma3:1b")

    connection = open_db(config.paths.db)
    try:
        rows = connection.execute("SELECT task, verdict FROM intervals ORDER BY task").fetchall()
    finally:
        connection.close()
    return [(str(row["task"]), str(row["verdict"])) for row in rows]


def test_a_reject_does_not_take_the_row_of_a_verified_interval(config) -> None:
    """The failure CodeRabbit flagged: the REJECT is second, and must lose."""
    rows = _persist_candidates(
        config,
        _accepted("Pre-Carbon filter replacement", 12, status="PASS", months=2.0, model_months=2.0),
        _rejected("Pre-Carbon filter replacement", 12, "quote_not_in_page"),
    )
    assert rows == [("Pre-Carbon filter replacement", "PASS")]


def test_the_row_keeps_the_answer_the_source_agreed_with(config) -> None:
    """The shape the corpus produced: one key, a PASS and a REPAIR.

    ``winix-5500`` p.1 named both answers "Clean once every 3 months", so the
    row can only hold one. The PASS is the answer the source agreed with.
    """
    rows = _persist_candidates(
        config,
        _accepted("Clean once every 3 months", 1, status="PASS", months=3.0, model_months=3.0),
        _accepted("Clean once every 3 months", 1, status="REPAIR", months=12.0, model_months=3.0),
    )
    assert rows == [("Clean once every 3 months", "PASS")]


def test_two_candidates_that_agree_still_keep_the_last_one(config) -> None:
    """Only the tie-breaks above are new; equals behave as they did."""
    rows = _persist_candidates(
        config,
        _accepted("Replace filters", 12, status="PASS", months=6.0, model_months=6.0),
        _accepted("Replace filters", 12, status="PASS", months=12.0, model_months=12.0),
    )
    assert rows == [("Replace filters", "PASS")]


def test_distinct_keys_are_separate_rows_and_skips_are_not_stored(config) -> None:
    """The dedup is by (device, task, page) only — it must not over-merge."""
    skipped = _candidate(
        "Clean the pre-filter", 12, Verdict(status="SKIP", reason="no_interval_stated")
    )
    rows = _persist_candidates(
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


def test_the_stored_count_is_the_number_of_rows_written(config, capsys) -> None:
    """``Stored N intervals`` must not overcount the rows it actually wrote."""
    _persist_candidates(
        config,
        _accepted("Replace filters", 12, status="PASS", months=6.0, model_months=6.0),
        _rejected("Replace filters", 12, "task_not_in_source"),
        _accepted("Replace the HEPA filter", 12, status="PASS", months=12.0, model_months=12.0),
    )
    printed = capsys.readouterr().out
    assert "Stored 2 intervals" in printed
