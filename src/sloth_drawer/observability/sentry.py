"""Sentry-backed tracing — optional, and off unless a DSN is configured.

``sentry_sdk`` lives in the ``observability`` extra (RULES.md 1.2) and is
imported **lazily**, inside :func:`init_tracing`. With ``SLOTH_SENTRY_DSN``
unset this module returns a :class:`NoOpTracer` and never imports the SDK, so
the core install pays nothing for it and a machine without the extra still runs
the whole pipeline.

The span vocabulary is fixed here, one span per pipeline stage
(ARCHITECTURE.md 4.5): ``ingest``, ``chunk``, ``prefilter``, ``triage``,
``extract``, ``verify``, ``persist``. Model spans additionally carry
``gen_ai.usage.input_tokens`` / ``gen_ai.usage.output_tokens``. Nothing else
crosses the boundary — see :mod:`sloth_drawer.observability.base` for why that
is enforced by the type rather than by convention.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sloth_drawer.config import Config
from sloth_drawer.observability.base import NoOpTracer, Span, Tracer

LOGGER = logging.getLogger("sloth_drawer.observability")

#: Every stage the pipeline can open. Kept as data so a test can pin the
#: vocabulary and so a typo in a call site can be caught by review.
STAGES = ("ingest", "chunk", "prefilter", "triage", "extract", "verify", "persist")

#: Sample every transaction. The corpus is small and the trace is the point.
TRACES_SAMPLE_RATE = 1.0

INSTALL_HINT = 'Install it with: pip install "sloth-drawer[observability]"'


class _SentrySpan:
    """The real span. Its only writes are numbers — see ``base.Span``."""

    def __init__(self, span: Any) -> None:
        self._span = span

    def set_data(self, key: str, value: int | float) -> None:
        self._span.set_data(key, value)

    def set_token_usage(self, *, input_tokens: int, output_tokens: int) -> None:
        self._span.set_data("gen_ai.usage.input_tokens", int(input_tokens))
        self._span.set_data("gen_ai.usage.output_tokens", int(output_tokens))


class SentryTracer:
    """Tracer backed by a configured ``sentry_sdk``."""

    enabled = True

    def __init__(self, sdk: Any) -> None:
        self._sdk = sdk

    @contextmanager
    def transaction(self, name: str, op: str = "pipeline") -> Iterator[None]:
        with self._sdk.start_transaction(op=op, name=name):
            yield

    @contextmanager
    def span(self, op: str, description: str = "") -> Iterator[Span]:
        with self._sdk.start_span(op=op, description=description) as span:
            yield _SentrySpan(span)

    def flush(self, timeout: float = 2.0) -> None:
        self._sdk.flush(timeout=timeout)


def init_tracing(config: Config) -> Tracer:
    """Build the tracer for this run.

    Returns a :class:`NoOpTracer` when there is no DSN, when the extra is not
    installed, or when Sentry rejects its configuration — an optional
    integration must never abort a scan. Each of those cases logs what to do
    instead of raising.
    """
    if not config.sentry_dsn:
        return NoOpTracer()

    try:
        import sentry_sdk  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        LOGGER.warning("Sentry tracing is configured but sentry-sdk is missing. %s", INSTALL_HINT)
        return NoOpTracer()

    try:
        sentry_sdk.init(
            dsn=config.sentry_dsn,
            traces_sample_rate=TRACES_SAMPLE_RATE,
            # The tool already refuses to send prompt text; this keeps Sentry
            # from enriching spans with request/user data as well.
            send_default_pii=False,
        )
    except Exception as exc:  # noqa: BLE001 - a broken optional integration must not stop a scan
        LOGGER.warning(
            "Sentry tracing disabled (%s: %s). %s", type(exc).__name__, exc, INSTALL_HINT
        )
        return NoOpTracer()

    LOGGER.info("Sentry tracing on (traces_sample_rate=%s).", TRACES_SAMPLE_RATE)
    return SentryTracer(sentry_sdk)


#: Re-exported so a caller can type against one module.
__all__ = ["STAGES", "SentryTracer", "Tracer", "init_tracing"]
