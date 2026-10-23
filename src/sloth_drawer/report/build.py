"""The accuracy report: ``report.json`` and ``report.md``.

This file is the post's data. Every number the write-up quotes comes from here,
which is why the report is built from the live scan result rather than
re-derived from the database: a rejected candidate that collapsed into another
row must still be counted.

The report is honest by construction. It counts what the verifier rejected and
why, and it records the manuals that were skipped with the reason, because a
run that quietly drops four scanned manuals is a run that cannot be trusted
(RULES.md 2.4).
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from sloth_drawer.config import Paths
from sloth_drawer.errors import ConfigError, StorageError
from sloth_drawer.pipeline import ScanResult
from sloth_drawer.storage.db import Device, now_iso


@dataclass(frozen=True)
class DeviceRow:
    """One line of the per-manual table."""

    manual: str
    device: str
    slug: str
    candidates: int
    passed: int
    repaired: int
    rejected: int
    skipped: int

    @property
    def found(self) -> int:
        return self.passed + self.repaired


@dataclass(frozen=True)
class SkippedRow:
    """A manual that was never read, and why."""

    file: str
    reason: str
    detail: str


@dataclass(frozen=True)
class Report:
    """Everything one scan measured."""

    generated_at: str
    model_id: str
    prompt_version: int
    #: The *configured* retrieval backend. The scan itself does not retrieve yet —
    #: the retriever is wired into the pipeline in Phase 4 — so this is recorded
    #: for the backend parity run, not as a claim about this run.
    backend: str
    manuals: int
    skipped_manuals: int
    chunks: int
    candidates: int
    found: int
    passed: int
    repaired: int
    rejected: int
    skipped: int
    seconds: float
    tokens: int
    cost_usd: float
    rejection_reasons: dict[str, int] = field(default_factory=dict)
    devices: tuple[DeviceRow, ...] = ()
    skipped_files: tuple[SkippedRow, ...] = ()

    def to_dict(self) -> dict:
        """The JSON shape. A flat document, so the post can read one number."""
        payload = asdict(self)
        payload["devices"] = [asdict(row) for row in self.devices]
        payload["skipped_files"] = [asdict(row) for row in self.skipped_files]
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2) + "\n"

    @property
    def summary(self) -> str:
        """The one line the post quotes."""
        return (
            f"{self.manuals} manuals · {self.found} intervals found · "
            f"{self.passed} verified · {self.repaired} repaired · "
            f"{self.rejected} rejected · {self.seconds:.0f}s · "
            f"{self.tokens} tokens · ${self.cost_usd:.2f}"
        )

    def table(self) -> str:
        """The console table: the report's own numbers, one row per manual."""
        header = f"{'MANUAL':<34} {'CAND':>4} {'PASS':>4} {'REP':>4} {'REJ':>4} {'SKIP':>4}"
        lines = [header, "-" * len(header)]
        for row in self.devices:
            lines.append(
                f"{row.manual:<34} {row.candidates:>4} {row.passed:>4} "
                f"{row.repaired:>4} {row.rejected:>4} {row.skipped:>4}"
            )
        lines.append("")
        lines.append(self.summary)
        if self.rejection_reasons:
            lines.append("")
            lines.append("Rejection reasons:")
            for reason, count in sorted(self.rejection_reasons.items()):
                lines.append(f"  {reason:<28} {count:>3}")
        return "\n".join(lines)

    def to_markdown(self) -> str:
        """The table that goes in the post."""
        lines = [
            "# Sloth Drawer — accuracy report",
            "",
            f"Generated {self.generated_at} · model `{self.model_id}` · "
            f"prompt v{self.prompt_version} · configured retrieval `{self.backend}`",
            "",
            f"**{self.summary}**",
            "",
            f"{self.chunks} chunks scored high enough in the pre-filter to reach the model, "
            f"producing {self.candidates} candidates.",
            "",
            "| Manual | Candidates | Passed | Repaired | Rejected | Skipped |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for row in self.devices:
            lines.append(
                f"| {row.manual} | {row.candidates} | {row.passed} | "
                f"{row.repaired} | {row.rejected} | {row.skipped} |"
            )
        lines.extend(
            [
                f"| **total** | **{self.candidates}** | **{self.passed}** | "
                f"**{self.repaired}** | **{self.rejected}** | **{self.skipped}** |",
                "",
            ]
        )
        if self.rejection_reasons:
            lines.extend(
                ["## Why candidates were rejected", "", "| Reason | Count |", "|---|---:|"]
            )
            for reason, count in sorted(self.rejection_reasons.items()):
                lines.append(f"| `{reason}` | {count} |")
            lines.append("")
        if self.skipped_files:
            lines.extend(["## Manuals skipped", "", "| File | Reason | Detail |", "|---|---|---|"])
            for entry in self.skipped_files:
                detail = entry.detail.replace("|", "/")
                lines.append(f"| {entry.file} | `{entry.reason}` | {detail} |")
            lines.append("")
        return "\n".join(lines) + "\n"


def from_scan(
    result: ScanResult,
    devices: tuple[Device, ...] = (),
    *,
    model_id: str,
    backend: str,
    prompt_version: int,
    generated_at: str | None = None,
    cost_usd: float = 0.0,
) -> Report:
    """Turn one scan into the report.

    A manual the scan never read still gets a row, so a skipped file cannot
    disappear from the totals.
    """
    names = {device.slug: device.name for device in devices}
    # A manual that was never read still has a device, if the registry knows it.
    by_manual = {device.manual_path: device for device in devices if device.manual_path is not None}
    counts: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    per_manual: dict[str, Counter[str]] = {}

    for candidate in result.candidates:
        counts[candidate.status] += 1
        per_manual.setdefault(candidate.manual_path, Counter())[candidate.status] += 1
        # Only a REJECT is a rejection. A triage SKIP is the gate saying "no",
        # which is a different outcome with a different meaning.
        if candidate.status == "REJECT" and candidate.verdict.reason:
            reasons[candidate.verdict.reason] += 1

    rows: list[DeviceRow] = []
    for manual in result.manuals:
        tally = per_manual.get(manual.path.name, Counter())
        rows.append(
            DeviceRow(
                manual=manual.path.name,
                device=names.get(manual.slug, manual.slug),
                slug=manual.slug,
                candidates=sum(tally.values()),
                passed=tally.get("PASS", 0),
                repaired=tally.get("REPAIR", 0),
                rejected=tally.get("REJECT", 0),
                skipped=tally.get("SKIP", 0),
            )
        )
    for skipped in result.skipped:
        known = by_manual.get(skipped.path.name)
        rows.append(
            DeviceRow(
                manual=skipped.path.name,
                device=known.name if known else skipped.path.name,
                slug=known.slug if known else "",
                candidates=0,
                passed=0,
                repaired=0,
                rejected=0,
                skipped=0,
            )
        )

    passed = counts.get("PASS", 0)
    repaired = counts.get("REPAIR", 0)
    return Report(
        generated_at=generated_at or now_iso(),
        model_id=model_id,
        prompt_version=prompt_version,
        backend=backend,
        manuals=len(result.manuals),
        skipped_manuals=len(result.skipped),
        chunks=result.chunks,
        candidates=len(result.candidates),
        found=passed + repaired,
        passed=passed,
        repaired=repaired,
        rejected=counts.get("REJECT", 0),
        skipped=counts.get("SKIP", 0),
        seconds=result.seconds,
        tokens=result.tokens,
        cost_usd=cost_usd,
        rejection_reasons=dict(reasons),
        devices=tuple(rows),
        skipped_files=tuple(
            SkippedRow(file=item.path.name, reason=item.reason, detail=item.detail)
            for item in result.skipped
        ),
    )


def write_report(report: Report, paths: Paths) -> tuple[Path, Path]:
    """Write ``out/report.json`` and ``out/report.md``. Returns both paths."""
    try:
        paths.out.mkdir(parents=True, exist_ok=True)
        paths.report_json.write_text(report.to_json(), encoding="utf-8")
        paths.report_md.write_text(report.to_markdown(), encoding="utf-8")
    except OSError as exc:
        raise StorageError(f"Could not write the report: {exc}") from exc
    return paths.report_json, paths.report_md


def load_report(path: Path) -> Report:
    """Read ``report.json`` back. Raises :class:`ConfigError` when it is absent."""
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"No report at {path}. Run `sloth-drawer scan <dir>` first.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Could not read {path}: {exc}") from exc

    return Report(
        generated_at=str(payload.get("generated_at", "")),
        model_id=str(payload.get("model_id", "")),
        prompt_version=int(payload.get("prompt_version", 0)),
        backend=str(payload.get("backend", "")),
        manuals=int(payload.get("manuals", 0)),
        skipped_manuals=int(payload.get("skipped_manuals", 0)),
        chunks=int(payload.get("chunks", 0)),
        candidates=int(payload.get("candidates", 0)),
        found=int(payload.get("found", 0)),
        passed=int(payload.get("passed", 0)),
        repaired=int(payload.get("repaired", 0)),
        rejected=int(payload.get("rejected", 0)),
        skipped=int(payload.get("skipped", 0)),
        seconds=float(payload.get("seconds", 0.0)),
        tokens=int(payload.get("tokens", 0)),
        cost_usd=float(payload.get("cost_usd", 0.0)),
        rejection_reasons=dict(payload.get("rejection_reasons") or {}),
        devices=tuple(DeviceRow(**row) for row in payload.get("devices") or ()),
        skipped_files=tuple(SkippedRow(**row) for row in payload.get("skipped_files") or ()),
    )
