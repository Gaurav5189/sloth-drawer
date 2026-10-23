"""Optional agent tracing (RULES.md 1.2, ARCHITECTURE.md 4.5).

Import :func:`init_tracing` from here; import :mod:`sloth_drawer.observability.base`
when you only need the interface. The Sentry implementation is loaded lazily so
that ``sentry_sdk`` — an optional extra — is never imported on the core path.
"""

from __future__ import annotations

from sloth_drawer.observability.base import NoOpTracer, Span, Tracer, null_span
from sloth_drawer.observability.sentry import STAGES, init_tracing

__all__ = ["NoOpTracer", "STAGES", "Span", "Tracer", "init_tracing", "null_span"]
