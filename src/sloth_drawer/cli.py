"""The command line. The only place in the project that prints.

Exit codes follow RULES.md 2.5: 0 success, 1 partial success (something was
rejected or skipped), 2 fatal (configuration or Ollama unreachable, nothing
written), 130 interrupted.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

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
)

LOGGER = logging.getLogger("sloth_drawer")


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
    scan.set_defaults(handler=_cmd_scan)

    return parser


def _cmd_scan(args: argparse.Namespace, config: Config) -> int:
    """Read a folder of manuals and print every interval the verifier accepted."""
    from sloth_drawer.models import check_ollama
    from sloth_drawer.pipeline import scan_corpus

    directory = Path(args.directory)
    if not directory.is_dir():
        raise ConfigError(f"Manual directory not found: {directory}")

    # Fail-fast if Ollama is unreachable — documented behaviour is exit 2,
    # not a batch of REJECT model_timeout rows.
    check_ollama(config.ollama_host)

    result = scan_corpus(
        directory,
        config=config,
        model=args.model,
        triage_model=args.triage_model,
        use_triage=args.triage,
        threshold=args.threshold,
        keep_alive=args.keep_alive,
    )

    for skipped in result.skipped:
        print(f"skipped  {skipped}", file=sys.stderr)

    counts = result.counts()
    print()
    print(f"{'MANUAL':<34} {'PAGE':>5}  {'VERDICT':<8} {'INTERVAL':<14} TASK")
    print("-" * 100)
    for candidate in result.candidates:
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

    rejected = result.rejected
    if rejected:
        print()
        print("Rejected:")
        for candidate in rejected:
            print(
                f"  {candidate.manual_path} p.{candidate.page}: "
                f"{candidate.verdict.reason} — {candidate.quote[:60]!r}"
            )

    print()
    print(
        f"{len(result.manuals)} manuals · {len(result.candidates)} candidates · "
        f"{counts.get('PASS', 0)} passed · {counts.get('REPAIR', 0)} repaired · "
        f"{counts.get('REJECT', 0)} rejected · {counts.get('SKIP', 0)} skipped · "
        f"{result.seconds:.0f}s · {result.tokens} tokens · $0"
    )
    print(f"Retries: {sum(c.retries for c in result.candidates)}")

    if rejected or result.skipped:
        return EXIT_PARTIAL
    return EXIT_OK


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
