"""The report: the numbers the post quotes.

The report is built from the live scan result, not re-derived from the
database, so a rejected candidate cannot collapse into another row and vanish
from the totals. These tests pin the counts, the reason breakdown, and the
round trip through ``report.json``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sloth_drawer.config import Paths
from sloth_drawer.corpus.ingest import Manual, Page, Skipped
from sloth_drawer.errors import ConfigError
from sloth_drawer.extract.verify import Verdict
from sloth_drawer.pipeline import Candidate, ScanResult
from sloth_drawer.report.build import Report, from_scan, load_report, write_report
from sloth_drawer.storage.db import Device


def _manual(name: str, slug: str) -> Manual:
    return Manual(
        slug=slug,
        path=Path(name),
        sha256="0" * 64,
        pages=(Page(number=1, text="text", source=name),),
    )


def _candidate(manual: str, slug: str, status: str, *, reason=None, page=1, task="task"):
    return Candidate(
        manual_slug=slug,
        manual_path=manual,
        page=page,
        section="4.2 Filter Maintenance",
        excerpt="…",
        task=task,
        quote="every 2 months",
        verdict=Verdict(status=status, reason=reason, page=page),
        model_id="gemma3:1b",
    )


def _result() -> ScanResult:
    result = ScanResult(
        manuals=[_manual("acme-1.pdf", "acme-1"), _manual("acme-2.pdf", "acme-2")],
        skipped=[Skipped(path=Path("scanned.pdf"), reason="no_text_layer", detail="image only")],
    )
    result.candidates = [
        _candidate("acme-1.pdf", "acme-1", "PASS"),
        _candidate("acme-1.pdf", "acme-1", "REPAIR", page=2),
        _candidate("acme-1.pdf", "acme-1", "REJECT", reason="quote_not_in_page", page=3),
        _candidate("acme-2.pdf", "acme-2", "REJECT", reason="quote_not_in_page", page=4),
        _candidate("acme-2.pdf", "acme-2", "SKIP", reason="no_interval_stated", page=5),
    ]
    result.seconds = 12.5
    result.tokens = 4200
    result.chunks = 41
    return result


def _devices() -> tuple[Device, ...]:
    return (
        Device(slug="acme-1", name="Acme One", manual_path="acme-1.pdf"),
        Device(slug="acme-2", name="Acme Two", manual_path="acme-2.pdf"),
        Device(slug="acme-3", name="Acme Three", manual_path="scanned.pdf"),
    )


def _report() -> Report:
    return from_scan(
        _result(),
        _devices(),
        model_id="gemma3:1b",
        backend="local",
        prompt_version=1,
        generated_at="2026-10-23T12:00:00+00:00",
    )


def test_the_totals_count_what_the_verifier_did() -> None:
    report = _report()
    assert report.manuals == 2
    assert report.skipped_manuals == 1
    assert report.candidates == 5
    assert report.passed == 1
    assert report.repaired == 1
    assert report.found == 2
    assert report.rejected == 2
    assert report.skipped == 1


def test_the_chunk_count_reaches_the_report() -> None:
    """The report says how much work the pre-filter let through, not just the outcome."""
    report = _report()
    assert report.chunks == 41
    assert report.to_dict()["chunks"] == 41
    assert "41 chunks" in report.to_markdown()


def test_the_summary_line_is_the_one_the_post_quotes() -> None:
    summary = _report().summary
    assert summary.startswith("2 manuals · 2 intervals found · 1 verified · 1 repaired")
    assert "12s" in summary
    assert "4200 tokens" in summary
    assert "$0.00" in summary


def test_rejection_reasons_exclude_triage_skips() -> None:
    """A triage "no" is a different outcome from a rejection, and is counted as one."""
    report = _report()
    assert report.rejection_reasons == {"quote_not_in_page": 2}
    assert "no_interval_stated" not in report.rejection_reasons


def test_every_manual_gets_a_row_including_the_skipped_one() -> None:
    report = _report()
    by_manual = {row.manual: row for row in report.devices}
    assert set(by_manual) == {"acme-1.pdf", "acme-2.pdf", "scanned.pdf"}
    assert by_manual["acme-1.pdf"].passed == 1
    assert by_manual["acme-1.pdf"].repaired == 1
    assert by_manual["acme-1.pdf"].rejected == 1
    assert by_manual["acme-2.pdf"].skipped == 1
    assert by_manual["scanned.pdf"].candidates == 0
    assert by_manual["scanned.pdf"].device == "Acme Three"
    assert by_manual["scanned.pdf"].slug == "acme-3"
    assert by_manual["acme-1.pdf"].device == "Acme One"


def test_the_markdown_table_has_the_totals_row() -> None:
    markdown = _report().to_markdown()
    assert "| Manual | Candidates | Passed | Repaired | Rejected | Skipped |" in markdown
    assert "| **total** | **5** | **1** | **1** | **2** | **1** |" in markdown
    assert "`quote_not_in_page` | 2" in markdown
    assert "`no_text_layer`" in markdown


def test_the_console_table_lists_each_manual() -> None:
    table = _report().table()
    assert "acme-1.pdf" in table
    assert "Rejection reasons:" in table
    assert "quote_not_in_page" in table


def test_the_report_round_trips_through_disk(tmp_path) -> None:
    paths = Paths(root=tmp_path)
    report = _report()
    json_path, md_path = write_report(report, paths)

    assert json_path == tmp_path / "out" / "report.json"
    assert md_path == tmp_path / "out" / "report.md"
    assert json_path.is_file() and md_path.is_file()

    reloaded = load_report(json_path)
    assert reloaded.to_dict() == report.to_dict()
    assert reloaded.devices == report.devices


def test_a_missing_report_says_what_to_run(tmp_path) -> None:
    with pytest.raises(ConfigError, match="sloth-drawer scan"):
        load_report(tmp_path / "nope.json")


def test_an_unreadable_report_is_a_configuration_error(tmp_path) -> None:
    path = tmp_path / "report.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError, match="Could not read"):
        load_report(path)
