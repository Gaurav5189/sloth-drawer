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
from sloth_drawer.models import check_ollama, is_available, model_registry

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

    return parser


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
