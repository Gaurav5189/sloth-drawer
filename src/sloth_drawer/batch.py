"""The batch runner: a whole corpus, one manual at a time, resumable.

``scan_corpus`` used to read every manual and then write once, at the end. That
is the wrong shape for the thing this tool actually is. A corpus of 19 manuals
is twenty minutes of CPU inference on a box with no GPU; a crash at manual 18
must not cost the user the first seventeen. So the batch runner changes three
things (RULES.md 2.6, PHASES.md Phase 3):

*   **one transaction per manual** — a manual's device row and every interval
    it produced commit together, or not at all, via
    :func:`sloth_drawer.storage.db.store_manual`;
*   **a checkpoint** — a small JSON file in ``out/`` records each manual's
    outcome and the SHA-256 of the file it came from, so ``--resume`` can skip
    manuals that are already done and unchanged; and
*   **progress** — the caller gets a callback per manual, so the CLI can print
    a line as each one lands rather than going quiet for twenty minutes.

A manual that cannot be read is recorded, not raised (RULES.md 2.4); a manual
that can is stored, and the checkpoint advances. The report is rebuilt from the
checkpoint, so a resumed run reports exactly what an unbroken one would.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

from sloth_drawer.config import Config
from sloth_drawer.corpus import prefilter
from sloth_drawer.corpus.chunk import chunk_manual
from sloth_drawer.corpus.ingest import list_pdfs, read_manual, sha256_of, slug_from_filename
from sloth_drawer.errors import ConfigError, CorpusError, NoTextLayerError, StorageError
from sloth_drawer.extract.prompts import PROMPT_VERSION
from sloth_drawer.models import DEFAULT_EXTRACTOR, DEFAULT_TRIAGE
from sloth_drawer.observability.base import NoOpTracer, Tracer
from sloth_drawer.pipeline import Candidate, scan_manual, stage
from sloth_drawer.report.build import ManualSummary, Report, from_summaries, write_report
from sloth_drawer.retrieval.base import ChunkIndexer
from sloth_drawer.storage.db import (
    Device,
    IntervalWrite,
    RunRecord,
    now_iso,
    open_db,
    record_run,
    store_manual,
    upsert_device,
)

LOGGER = logging.getLogger("sloth_drawer.batch")

#: Where the checkpoint lives, relative to ``out/``.
CHECKPOINT_NAME = "batch.json"

#: Bumped if the checkpoint shape changes, so an old file is rebuildable.
CHECKPOINT_VERSION = 1

#: How strongly a candidate claims the single row its ``(task, page)`` key
#: allows. A REJECT must never take a row a verified interval is holding; between
#: two verified answers, PASS is the one the source agreed with.
_PRIORITY = {"PASS": 2, "REPAIR": 1}


@dataclass(frozen=True)
class ManualOutcome:
    """One manual's result, in the shape the checkpoint stores."""

    manual: str
    slug: str
    sha256: str = ""
    status: str = "done"  # done | skipped
    reason: str = ""
    detail: str = ""
    pages: int = 0
    chunks: int = 0
    candidates: int = 0
    passed: int = 0
    repaired: int = 0
    rejected: int = 0
    skipped: int = 0
    rejection_reasons: dict[str, int] = field(default_factory=dict)
    embed_failed: int = 0
    index_failed: int = 0
    seconds: float = 0.0
    tokens: int = 0

    @property
    def found(self) -> int:
        return self.passed + self.repaired

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> ManualOutcome:
        """Read a checkpoint row tolerantly: unknown keys are ignored."""
        fields = {
            key: payload[key]
            for key in (
                "manual",
                "slug",
                "sha256",
                "status",
                "reason",
                "detail",
                "pages",
                "chunks",
                "candidates",
                "passed",
                "repaired",
                "rejected",
                "skipped",
                "rejection_reasons",
                "embed_failed",
                "index_failed",
                "seconds",
                "tokens",
            )
            if key in payload
        }
        return cls(**fields)


@dataclass
class Checkpoint:
    """Which manuals are finished, and what each produced."""

    started_at: str
    updated_at: str
    model_id: str
    backend: str
    outcomes: dict[str, ManualOutcome] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "version": CHECKPOINT_VERSION,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "model_id": self.model_id,
            "backend": self.backend,
            "manuals": {name: outcome.to_dict() for name, outcome in self.outcomes.items()},
        }

    def save(self, path: Path) -> None:
        """Write the checkpoint atomically, so a crash cannot corrupt it."""
        path = Path(path)
        temporary = path.parent / f"{path.name}.tmp"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
            temporary.replace(path)
        except OSError as exc:
            raise StorageError(f"Could not write the checkpoint at {path}: {exc}") from exc

    @classmethod
    def load(cls, path: Path) -> Checkpoint | None:
        """Read a checkpoint, or ``None`` when none exists.

        A corrupt checkpoint is an error, not a silent fresh start: quietly
        reprocessing (or, worse, skipping) is exactly the sort of surprise the
        resume feature must not introduce.
        """
        path = Path(path)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StorageError(
                f"Could not read the checkpoint at {path}: {exc}. Delete it to start fresh."
            ) from exc
        if not isinstance(payload, dict):
            raise StorageError(
                f"The checkpoint at {path} is not a JSON object. Delete it to start fresh."
            )

        raw = payload.get("manuals")
        outcomes: dict[str, ManualOutcome] = {}
        if isinstance(raw, dict):
            for name, entry in raw.items():
                if isinstance(entry, dict):
                    outcomes[str(name)] = ManualOutcome.from_dict(entry)
        return cls(
            started_at=str(payload.get("started_at", "")),
            updated_at=str(payload.get("updated_at", "")),
            model_id=str(payload.get("model_id", "")),
            backend=str(payload.get("backend", "")),
            outcomes=outcomes,
        )


@dataclass(frozen=True)
class Progress:
    """One line of progress, handed to the caller after each manual."""

    index: int
    total: int
    manual: str
    status: str  # done | skipped | resumed
    candidates: int = 0
    passed: int = 0
    repaired: int = 0
    rejected: int = 0
    seconds: float = 0.0


@dataclass
class BatchOutcome:
    """Everything one batch produced."""

    report: Report
    outcomes: tuple[ManualOutcome, ...]
    #: Candidates from the manuals processed *this* run. Resumed manuals remain
    #: in the database but are not re-listed.
    candidates: tuple[Candidate, ...]
    processed: int
    resumed: int
    checkpoint_path: Path


def _outranks(candidate: Candidate, held: Candidate) -> bool:
    """Whether ``candidate`` should take the one row its key allows."""
    return _PRIORITY.get(candidate.status, 0) >= _PRIORITY.get(held.status, 0)


def winner_rows(candidates: Sequence[Candidate], slug: str, *, model: str) -> list[IntervalWrite]:
    """Reduce candidates to one winner per ``(task, page)`` key.

    ``intervals`` is unique on ``(device_id, task, page)`` (RULES.md 2.6) but
    candidates are not: two excerpts of one chunk can name the same task, and a
    failed extraction is stored under the task name ``""``. Which one holds the
    row must not depend on scan order, so an accepted answer beats a rejected
    one and, between two accepted answers, PASS beats REPAIR.
    """
    chosen: dict[tuple[str, int | None], Candidate] = {}
    for candidate in candidates:
        if candidate.manual_slug != slug or candidate.status == "SKIP":
            continue
        key = (candidate.task, candidate.page)
        held = chosen.get(key)
        if held is None or _outranks(candidate, held):
            chosen[key] = candidate
    return [
        IntervalWrite(
            task=candidate.task,
            section=candidate.section,
            page=candidate.page,
            interval_months=candidate.verdict.interval_months,
            model_interval_months=candidate.verdict.model_interval_months,
            evidence=candidate.verdict.evidence,
            model_quote=candidate.quote or candidate.verdict.model_quote,
            verdict=candidate.verdict.status,
            reject_reason=candidate.verdict.reason,
            model_id=candidate.model_id or model,
            prompt_hash=str(PROMPT_VERSION),
        )
        for candidate in chosen.values()
    ]


def store_scan(
    connection: sqlite3.Connection,
    device: Device,
    candidates: Sequence[Candidate],
    *,
    model: str,
) -> int:
    """Store one manual's intervals in a single transaction. Returns rows written."""
    rows = winner_rows(candidates, device.slug, model=model)
    store_manual(connection, device, rows)
    return len(rows)


def _tally(candidates: Sequence[Candidate]) -> dict[str, int]:
    tally: dict[str, int] = {}
    for candidate in candidates:
        tally[candidate.status] = tally.get(candidate.status, 0) + 1
    return tally


def _reasons(candidates: Sequence[Candidate]) -> dict[str, int]:
    reasons: dict[str, int] = {}
    for candidate in candidates:
        if candidate.status == "REJECT" and candidate.verdict.reason:
            reasons[candidate.verdict.reason] = reasons.get(candidate.verdict.reason, 0) + 1
    return reasons


def _open_checkpoint(
    path: Path, *, resume: bool, force: bool, model: str, backend: str
) -> Checkpoint:
    """Load a checkpoint for ``--resume``, or start a fresh one."""
    if resume and not force:
        existing = Checkpoint.load(path)
        if existing is not None:
            if existing.model_id != model or existing.backend != backend:
                raise ConfigError(
                    f"The checkpoint at {path} was written with model "
                    f"{existing.model_id!r} and backend {existing.backend!r}; this run uses "
                    f"{model!r} and {backend!r}. Re-run with --force to restart, or delete "
                    f"the checkpoint."
                )
            return existing
    now = now_iso()
    return Checkpoint(started_at=now, updated_at=now, model_id=model, backend=backend)


def _resumable(resume: bool, prior: ManualOutcome | None, sha256: str) -> bool:
    """Whether a manual can be skipped: only when asked, and only if unchanged."""
    return bool(resume and prior is not None and prior.sha256 == sha256)


def _summary(outcome: ManualOutcome, by_manual: dict[str, Device]) -> ManualSummary:
    """Turn a checkpoint row into the report's per-manual summary."""
    device = by_manual.get(outcome.manual)
    skipped = outcome.status == "skipped"
    return ManualSummary(
        manual=outcome.manual,
        device=device.name if device else outcome.slug,
        slug=device.slug if device else outcome.slug,
        candidates=outcome.candidates,
        passed=outcome.passed,
        repaired=outcome.repaired,
        rejected=outcome.rejected,
        skipped=outcome.skipped,
        chunks=outcome.chunks,
        seconds=outcome.seconds,
        tokens=outcome.tokens,
        rejection_reasons=dict(outcome.rejection_reasons),
        embed_failed=outcome.embed_failed,
        index_failed=outcome.index_failed,
        skipped_reason=outcome.reason if skipped else None,
        skipped_detail=outcome.detail if skipped else "",
    )


def _open_index_backend(
    config: Config, connection: sqlite3.Connection | None
) -> ChunkIndexer | None:
    """The chunk index the run writes to, or ``None`` without a state database.

    Configuration decides (RULES.md 6): ``tiger`` when the DSN is set, local
    FTS5 otherwise, both behind the same ``index_chunks`` call. A cloud backend
    that cannot be reached fails the run *here*, with the remediation in the
    message — never as a silent per-manual degradation (RULES.md 2.4a).
    """
    if connection is None:
        return None
    if config.use_tiger:
        from sloth_drawer.vector.indexer import CloudIndex

        cloud: ChunkIndexer = CloudIndex.from_env(config)
        return cloud
    from sloth_drawer.retrieval.local import LocalRetriever

    local: ChunkIndexer = LocalRetriever(connection)
    return local


def _scan_one(
    path: Path,
    sha256: str,
    *,
    config: Config,
    device: Device | None,
    model: str,
    triage_model: str | None,
    use_triage: bool,
    threshold: int,
    keep_alive: str | int | None,
    connection: sqlite3.Connection | None,
    index_backend: ChunkIndexer | None = None,
    tracer: Tracer,
) -> tuple[ManualOutcome, list[Candidate]]:
    """Read, scan and persist a single manual inside one transaction."""
    slug = device.slug if device is not None else slug_from_filename(path)
    with tracer.transaction(f"scan {path.name}", op="manual"):
        with stage(tracer, "ingest", "pypdf -> pages") as span:
            try:
                manual = read_manual(path, slug)
            except (CorpusError, NoTextLayerError) as exc:
                LOGGER.warning("skipped %s: %s", path.name, exc)
                # The manual could not be read, but the device is still real:
                # registering it lets `card` print the "interval not found"
                # card instead of claiming the device was never scanned.
                if connection is not None and device is not None:
                    with stage(tracer, "persist", "device row only"):
                        upsert_device(connection, device)
                return (
                    ManualOutcome(
                        manual=path.name,
                        slug=slug,
                        sha256=sha256,
                        status="skipped",
                        reason=exc.reason,
                        detail=str(exc),
                    ),
                    [],
                )
            span.set_data("pages.read", manual.page_count)

        started = time.monotonic()
        scanned = scan_manual(
            manual,
            config=config,
            model=model,
            triage_model=triage_model,
            use_triage=use_triage,
            threshold=threshold,
            keep_alive=keep_alive,
            tracer=tracer,
        )
        seconds = time.monotonic() - started

        if connection is not None and device is not None:
            with stage(tracer, "persist", "one transaction per manual") as span:
                span.set_data(
                    "intervals.written",
                    store_scan(connection, device, scanned.candidates, model=model),
                )

        tally = _tally(scanned.candidates)
        embed_failed = 0
        index_failed = 0
        if index_backend is not None:
            # The retrieval backend gets chunk text (page, section, content)
            # and nothing else: this call is the whole cloud boundary
            # (RULES.md 3.1a). A failed chunk is recorded, never a crash — but
            # it *is* a partial outcome, so the report and the exit code say so.
            with stage(tracer, "index", "chunks -> retrieval backend") as span:
                counts = index_backend.index_chunks(
                    sha256,
                    slug,
                    [
                        (chunk.page, chunk.section, chunk.text)
                        for chunk in chunk_manual(manual.pages)
                    ],
                )
                embed_failed = counts.get("embed_failed", 0)
                index_failed = counts.get("index_failed", 0)
                span.set_data("chunks.indexed", counts.get("indexed", 0))
        return (
            ManualOutcome(
                manual=path.name,
                slug=slug,
                sha256=sha256,
                status="done",
                pages=manual.page_count,
                chunks=scanned.chunks,
                candidates=len(scanned.candidates),
                passed=tally.get("PASS", 0),
                repaired=tally.get("REPAIR", 0),
                rejected=tally.get("REJECT", 0),
                skipped=tally.get("SKIP", 0),
                rejection_reasons=_reasons(scanned.candidates),
                embed_failed=embed_failed,
                index_failed=index_failed,
                seconds=seconds,
                tokens=sum(candidate.tokens for candidate in scanned.candidates),
            ),
            scanned.candidates,
        )


def run_batch(
    directory: Path,
    *,
    config: Config,
    devices: Sequence[Device] = (),
    model: str = DEFAULT_EXTRACTOR,
    triage_model: str | None = DEFAULT_TRIAGE,
    use_triage: bool = False,
    threshold: int = prefilter.DEFAULT_THRESHOLD,
    keep_alive: str | int | None = None,
    resume: bool = False,
    force: bool = False,
    persist: bool = True,
    tracer: Tracer | None = None,
    progress: Callable[[Progress], None] | None = None,
) -> BatchOutcome:
    """Scan a directory, one manual per transaction, and write the report.

    ``resume`` skips manuals the checkpoint already holds with the same
    SHA-256; ``force`` starts fresh even when both are set. ``persist=False``
    scans without touching the database or writing a report.
    """
    pdfs = list_pdfs(directory)
    checkpoint_path = config.paths.out / CHECKPOINT_NAME
    checkpoint = _open_checkpoint(
        checkpoint_path,
        resume=resume,
        force=force,
        model=model,
        backend=config.retrieval,
    )
    by_manual = {device.manual_path: device for device in devices if device.manual_path is not None}
    tracer = tracer or NoOpTracer()

    processed = 0
    resumed = 0
    extracted: list[Candidate] = []
    connection = open_db(config.paths.db) if persist else None
    index_backend = _open_index_backend(config, connection)
    try:
        for index, path in enumerate(pdfs, start=1):
            sha256 = sha256_of(path)
            prior = checkpoint.outcomes.get(path.name)
            if prior is not None and _resumable(resume, prior, sha256):
                resumed += 1
                _emit(progress, _progress(index, len(pdfs), "resumed", prior))
                continue

            processed += 1
            outcome, candidates = _scan_one(
                path,
                sha256,
                config=config,
                device=by_manual.get(path.name),
                model=model,
                triage_model=triage_model,
                use_triage=use_triage,
                threshold=threshold,
                keep_alive=keep_alive,
                connection=connection,
                index_backend=index_backend,
                tracer=tracer,
            )
            checkpoint.outcomes[path.name] = outcome
            checkpoint.updated_at = now_iso()
            if persist:
                checkpoint.save(checkpoint_path)
            extracted.extend(candidates)
            _emit(progress, _progress(index, len(pdfs), outcome.status, outcome))

        summaries = [
            _summary(checkpoint.outcomes[path.name], by_manual)
            for path in pdfs
            if path.name in checkpoint.outcomes
        ]
        report = from_summaries(
            summaries,
            model_id=model,
            backend=config.retrieval,
            prompt_version=PROMPT_VERSION,
        )
        if persist and connection is not None:
            record_run(
                connection,
                RunRecord(
                    started_at=checkpoint.started_at,
                    finished_at=now_iso(),
                    model_id=model,
                    backend=config.retrieval,
                    manuals=report.manuals,
                    chunks=report.chunks,
                    candidates=report.candidates,
                    found=report.found,
                    passed=report.passed,
                    repaired=report.repaired,
                    rejected=report.rejected,
                    seconds=report.seconds,
                    tokens=report.tokens,
                ),
            )
            write_report(report, config.paths)
    finally:
        if connection is not None:
            connection.close()

    return BatchOutcome(
        report=report,
        outcomes=tuple(
            checkpoint.outcomes[path.name] for path in pdfs if path.name in checkpoint.outcomes
        ),
        candidates=tuple(extracted),
        processed=processed,
        resumed=resumed,
        checkpoint_path=checkpoint_path,
    )


def _progress(index: int, total: int, status: str, outcome: ManualOutcome) -> Progress:
    return Progress(
        index=index,
        total=total,
        manual=outcome.manual,
        status=status,
        candidates=outcome.candidates,
        passed=outcome.passed,
        repaired=outcome.repaired,
        rejected=outcome.rejected,
        seconds=outcome.seconds,
    )


def _emit(callback: Callable[[Progress], None] | None, event: Progress) -> None:
    if callback is not None:
        callback(event)


__all__ = [
    "BatchOutcome",
    "CHECKPOINT_NAME",
    "Checkpoint",
    "ManualOutcome",
    "Progress",
    "run_batch",
    "store_scan",
    "winner_rows",
]
