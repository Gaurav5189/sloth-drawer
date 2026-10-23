"""The command line. The only place in the project that prints.

Exit codes follow RULES.md 2.5: 0 success, 1 partial success (something was
rejected or skipped, or a card could not state an interval), 2 fatal
(configuration or Ollama unreachable, nothing written), 130 interrupted.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from sloth_drawer import __version__
from sloth_drawer.config import Config, load_config
from sloth_drawer.errors import (
    EXIT_FATAL,
    EXIT_INTERRUPTED,
    EXIT_OK,
    EXIT_PARTIAL,
    ConfigError,
    SlothDrawerError,
)
from sloth_drawer.models import (
    DEFAULT_EXTRACTOR,
    DEFAULT_TRIAGE,
    check_ollama,
    is_available,
    model_registry,
    require_model,
)

LOGGER = logging.getLogger("sloth_drawer")

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from sloth_drawer.pipeline import Candidate
    from sloth_drawer.storage.db import Device


def build_parser() -> argparse.ArgumentParser:
    """The argument parser for every subcommand."""
    parser = argparse.ArgumentParser(
        prog="sloth-drawer",
        description="Read the manual PDFs you already own and print one card per device.",
    )
    parser.add_argument("--version", action="version", version=f"sloth-drawer {__version__}")
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="library logging level (the CLI itself prints to stdout)",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    models = subcommands.add_parser(
        "models",
        help="list the model registry with the measured sizes and latencies",
    )
    models.add_argument("--json", action="store_true", help="machine-readable output")
    models.set_defaults(handler=_cmd_models)

    scan = subcommands.add_parser(
        "scan",
        help="read a directory of manual PDFs and print the verified intervals",
    )
    scan.add_argument("directory", help="the folder holding the manual PDFs")
    scan.add_argument(
        "--model",
        default=DEFAULT_EXTRACTOR,
        help=f"the extraction model (default: {DEFAULT_EXTRACTOR})",
    )
    scan.add_argument(
        "--triage-model",
        default=DEFAULT_TRIAGE,
        help=f"the triage model (default: {DEFAULT_TRIAGE})",
    )
    scan.add_argument(
        "--triage",
        action="store_true",
        help=(
            "gate candidates through the small triage model first. Off by default: "
            "the pre-filter already removes most chunks, and a weak gate can lose "
            "intervals the extractor would have found"
        ),
    )
    scan.add_argument(
        "--threshold",
        type=int,
        default=2,
        help="the pre-filter score a chunk must reach to reach the model",
    )
    scan.add_argument(
        "--keep-alive",
        default=None,
        help="how long Ollama keeps the model loaded (e.g. 5m, or 0 to unload)",
    )
    scan.add_argument(
        "--resume",
        action="store_true",
        help=(
            "skip manuals already completed in out/batch.json with the same SHA-256. "
            "For finishing a run that was interrupted"
        ),
    )
    scan.add_argument(
        "--force",
        action="store_true",
        help="start fresh even if a checkpoint exists (the default)",
    )
    scan.add_argument(
        "--list",
        action="store_true",
        help="print every accepted interval with its page citation",
    )
    scan.add_argument(
        "--no-persist",
        action="store_true",
        help="do not write the intervals to the local database or the report",
    )
    scan.set_defaults(handler=_cmd_scan)

    card = subcommands.add_parser("card", help="print one device's card and write it as HTML")
    card.add_argument("device", help="the device slug from data/devices.toml (or its name)")
    card.add_argument("--ascii", action="store_true", help="ASCII box drawing and glyphs")
    card.add_argument("--no-color", action="store_true", help="disable ANSI colour entirely")
    card.add_argument(
        "--out",
        default=None,
        help="where to write the HTML card (default: out/cards)",
    )
    card.set_defaults(handler=_cmd_card)

    done = subcommands.add_parser(
        "done", help="log that a task was done, and recompute the due date"
    )
    done.add_argument("device", help="the device slug from data/devices.toml (or its name)")
    done.add_argument("task", help="the task, as it appears on the card")
    done.add_argument(
        "--date",
        default=None,
        help="the date it was done, in YYYY-MM-DD form (default: today)",
    )
    done.add_argument("--note", default=None, help="an optional note")
    done.set_defaults(handler=_cmd_done)

    report = subcommands.add_parser("report", help="print the accuracy table from the last scan")
    report.add_argument("--json", action="store_true", help="print report.json instead")
    report.set_defaults(handler=_cmd_report)

    return parser


def _cmd_scan(args: argparse.Namespace, config: Config) -> int:
    """Read a folder of manuals, one transaction per manual, and report.

    The scan is the batch runner (``sloth_drawer.batch``): it checkpoints each
    manual so ``--resume`` can finish an interrupted run, and it writes the
    report from that checkpoint.
    """
    from sloth_drawer.batch import run_batch
    from sloth_drawer.observability import init_tracing
    from sloth_drawer.storage.db import load_devices

    directory = Path(args.directory)
    if not directory.is_dir():
        raise ConfigError(f"Manual directory not found: {directory}")

    # Fail fast if Ollama is unreachable or a model is not pulled — documented
    # behaviour is exit 2, not a batch of REJECT model_timeout rows.
    check_ollama(config.ollama_host)
    require_model(args.model, config.ollama_host, config.ollama_timeout)
    if args.triage:
        require_model(args.triage_model, config.ollama_host, config.ollama_timeout)

    devices: tuple[Device, ...] = ()
    if config.paths.devices_toml.is_file():
        devices = load_devices(config.paths.devices_toml)
    else:
        LOGGER.warning(
            "no device registry at %s; manuals are read but nothing is stored",
            config.paths.devices_toml,
        )

    tracer = init_tracing(config)

    def show(progress) -> None:
        width = len(str(progress.total))
        head = f"[{progress.index:>{width}}/{progress.total}]"
        if progress.status == "resumed":
            print(f"{head} resumed {progress.manual} (unchanged)", flush=True)
        elif progress.status == "skipped":
            print(f"{head} skipped {progress.manual}", flush=True)
        else:
            print(
                f"{head} done    {progress.manual}: {progress.candidates} candidates, "
                f"{progress.passed}P {progress.repaired}C {progress.rejected}R, "
                f"{progress.seconds:.0f}s",
                flush=True,
            )

    outcome = run_batch(
        directory,
        config=config,
        devices=devices,
        model=args.model,
        triage_model=args.triage_model,
        use_triage=args.triage,
        threshold=args.threshold,
        keep_alive=args.keep_alive,
        resume=args.resume,
        force=args.force,
        persist=not args.no_persist,
        tracer=tracer,
        progress=show,
    )
    tracer.flush()

    if args.list:
        if outcome.resumed:
            print(
                f"\nnote: {outcome.resumed} resumed manual(s) are not listed below; "
                "their intervals are in the report and the database."
            )
        _print_candidates(outcome.candidates)

    report = outcome.report
    print()
    print(report.table())
    if not args.no_persist:
        print()
        print(f"Checkpoint: {outcome.checkpoint_path} · database: {config.paths.db}")
        print(f"Report: {config.paths.report_json} · {config.paths.report_md}")

    if report.rejected or report.skipped_manuals:
        return EXIT_PARTIAL
    return EXIT_OK


def _print_candidates(candidates: Sequence[Candidate]) -> None:
    """List the accepted intervals with their citation, for hand-checking."""
    print()
    print(f"{'MANUAL':<34} {'PAGE':>5}  {'VERDICT':<8} {'INTERVAL':<14} TASK")
    print("-" * 100)
    for candidate in candidates:
        if not candidate.verdict.accepted:
            continue
        interval = candidate.verdict.interval
        shown = interval.display if interval else "—"
        task = candidate.task or "(untitled)"
        print(
            f"{candidate.manual_path:<34} {candidate.page:>5}  "
            f"{candidate.status:<8} {shown:<14} {task}"
        )
        if candidate.verdict.evidence:
            print(f'{"":<41} "{" ".join(candidate.verdict.evidence.split())}"')
        if candidate.verdict.disagreement:
            print(f"{'':<41} {candidate.verdict.disagreement}")


def _cmd_card(args: argparse.Namespace, config: Config) -> int:
    """Print one device's card and write the printable HTML beside it."""
    from sloth_drawer.render import card_filename, render_card_html, render_card_text
    from sloth_drawer.storage.service_log import schedule_for_device

    device = _resolve_device(args.device, config)
    connection = _open_state(config)
    try:
        row = _device_row(connection, device.slug)
        tasks = schedule_for_device(connection, int(row["id"]))
    finally:
        connection.close()

    from sloth_drawer.render import theme

    color = theme.supports_color(sys.stdout, disabled=args.no_color)
    print(render_card_text(device, tasks, color=color, ascii_only=args.ascii), end="")

    out_dir = Path(args.out) if args.out else config.paths.cards
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / card_filename(device)
        path.write_text(render_card_html(device, tasks), encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Could not write the card: {exc}") from exc
    print(f"\nHTML card: {path}")

    return EXIT_OK if any(task.accepted for task in tasks) else EXIT_PARTIAL


def _cmd_done(args: argparse.Namespace, config: Config) -> int:
    """Log a service event and recompute the due date in code."""
    from sloth_drawer.storage.service_log import (
        format_date,
        last_done,
        next_due,
        parse_date,
        record_done,
        schedule_for_device,
    )

    device = _resolve_device(args.device, config)
    connection = _open_state(config)
    try:
        row = _device_row(connection, device.slug)
        tasks = [task for task in schedule_for_device(connection, int(row["id"])) if task.accepted]
        if not tasks:
            raise ConfigError(f"{device.name} has no verified interval to log a service against.")
        match = _match_task(tasks, args.task)
        recorded = record_done(
            connection,
            match.interval_id,
            done_at=parse_date(args.date),
            note=args.note,
        )
        # The schedule runs from the *latest* service, which is not necessarily
        # the one just logged: an older date must not move the due date back.
        effective = last_done(connection, match.interval_id) or recorded
    finally:
        connection.close()

    due = next_due(effective, match.interval_months)
    print(f"Recorded {format_date(recorded)}: {device.name} — {match.task}")
    if effective != recorded:
        print(f"Latest service on record is {format_date(effective)}; the schedule uses that.")
    if due is None:
        print("No interval to schedule from; the card will show no due date.")
    else:
        print(f"Next due {format_date(due)} (every {match.display})")
    return EXIT_OK


def _cmd_report(args: argparse.Namespace, config: Config) -> int:
    """Print the accuracy table from the last scan."""
    from sloth_drawer.report.build import load_report

    report = load_report(config.paths.report_json)
    if args.json:
        print(report.to_json(), end="")
    else:
        print(report.table())
    if report.rejected or report.skipped_manuals:
        return EXIT_PARTIAL
    return EXIT_OK


def _resolve_device(key: str, config: Config):
    """Find a device by slug or by name.

    A slug is exact. A name is matched case-insensitively, and then as a unique
    substring, so ``hpa3000`` finds ``honeywell-hpa3000`` but an ambiguous
    fragment is an error rather than a guess.
    """
    from sloth_drawer.storage.db import load_devices

    devices = load_devices(config.paths.devices_toml)
    lowered = key.strip().lower()

    for device in devices:
        if device.slug == key:
            return device
    for device in devices:
        if device.name.lower() == lowered:
            return device

    matches = [
        device
        for device in devices
        if lowered in device.slug.lower() or lowered in device.name.lower()
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ConfigError(
            f"No device matches {key!r}. Known devices: "
            + ", ".join(device.slug for device in devices)
        )
    raise ConfigError(f"{key!r} is ambiguous: " + ", ".join(device.slug for device in matches))


def _match_task(tasks, key: str):
    """Find one task on a card by name.

    Exact match first, then a unique substring. A task that cannot be resolved
    is an error listing the card's tasks, never a guess about which filter the
    user meant.
    """
    lowered = key.strip().lower()
    for task in tasks:
        if task.task.lower() == lowered:
            return task
    matches = [task for task in tasks if lowered in task.task.lower()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ConfigError(
            f"No task matches {key!r} on this device. Known tasks: "
            + "; ".join(task.task for task in tasks)
        )
    raise ConfigError(f"{key!r} is ambiguous: " + "; ".join(task.task for task in matches))


def _device_row(connection, slug: str):
    """The device's stored row, or an explanation of what to run first."""
    row = connection.execute("SELECT id FROM devices WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        raise ConfigError(f"No scan data for {slug!r} yet. Run `sloth-drawer scan <dir>` first.")
    return row


def _open_state(config: Config):
    """Open the database the last scan wrote, or explain what to run first."""
    from sloth_drawer.storage.db import open_db

    if not config.paths.db.is_file():
        raise ConfigError(
            f"No scan data at {config.paths.db}. Run `sloth-drawer scan <dir>` first."
        )
    return open_db(config.paths.db)


def _cmd_models(args: argparse.Namespace, config: Config) -> int:
    """Show the registry and whether each model is pulled on the local server."""
    pulled = check_ollama(config.ollama_host, timeout=config.ollama_timeout)
    specs = model_registry()

    if args.json:
        payload = [
            {
                "model_id": spec.model_id,
                "role": spec.role,
                "size_mb": spec.size_mb,
                "latency_s": spec.latency_s,
                "tokens_per_s": spec.tokens_per_s,
                "note": spec.note,
                "pulled": is_available(spec.model_id, pulled),
            }
            for spec in specs
        ]
        print(json.dumps(payload, indent=2))
        return EXIT_OK

    header = f"{'MODEL':<22} {'ROLE':<22} {'SIZE':>8}  {'LATENCY':<12} {'TOK/S':<8} STATUS"
    print(header)
    print("-" * len(header))
    for spec in specs:
        status = "pulled" if is_available(spec.model_id, pulled) else "not pulled"
        print(
            f"{spec.model_id:<22} {spec.role:<22} {spec.size_display:>8}  "
            f"{spec.latency_s:<12} {spec.tokens_per_s:<8} {status}"
        )
    print()
    print(f"Ollama: {config.ollama_host}  ·  retrieval backend: {config.retrieval}")
    missing = [spec.model_id for spec in specs if not is_available(spec.model_id, pulled)]
    if missing:
        print(f"Missing: {', '.join(missing)}  —  ollama pull {' '.join(missing)}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """Parse the arguments, run the subcommand, and map failures to exit codes."""
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(levelname)s %(name)s: %(message)s")
    # pypdf warns about embedded fonts on almost every real manual; the warning
    # is not actionable and buries the output that matters.
    logging.getLogger("pypdf").setLevel(logging.ERROR)

    try:
        config = load_config()
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FATAL

    try:
        return int(args.handler(args, config))
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FATAL
    except SlothDrawerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FATAL
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return EXIT_INTERRUPTED


__all__ = ["build_parser", "main", "EXIT_OK", "EXIT_PARTIAL", "EXIT_FATAL", "EXIT_INTERRUPTED"]
