"""The tracing interface: one shape, a real backend and a no-op one.

The pipeline depends on this module and on nothing else in ``observability``.
That keeps the dependency arrow pointing at an abstract protocol — the pipeline
does not know whether Sentry is listening, and a machine with no DSN and no
``sentry_sdk`` runs the identical code path (RULES.md 1.2).

What a span may carry is deliberately narrow. ``Span`` exposes exactly two
writes:

*   ``set_data(key, value)`` — a **numeric** count, such as how many chunks the
    pre-filter let through; and
*   ``set_token_usage`` — the model's input/output token counts, recorded as
    the ``gen_ai.usage.*`` attributes the Sentry AI-agent view expects.

There is no method that takes free text, so the prompt, the excerpt, the model's
answer, a device name and a filesystem path are all **unrepresentable** in a
span. The privacy boundary in RULES.md 3.1a is therefore a property of the type,
not of the discipline of the call sites.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Protocol, runtime_checkable


@runtime_checkable
class Span(Protocol):
    """One timed stage, carrying numbers only."""

    def set_data(self, key: str, value: int | float) -> None:
        """Attach a numeric measurement (a count, a duration, a ratio)."""
        ...

    def set_token_usage(self, *, input_tokens: int, output_tokens: int) -> None:
        """Attach the model's token accounting to this span."""
        ...


@runtime_checkable
class Tracer(Protocol):
    """A tracing backend. ``enabled`` is False for the no-op implementation."""

    enabled: bool

    def transaction(self, name: str, op: str = "pipeline") -> AbstractContextManager[None]:
        """Open one transaction around a unit of work (here: one manual)."""
        ...

    def span(self, op: str, description: str = "") -> AbstractContextManager[Span]:
        """Open a span inside the current transaction."""
        ...

    def flush(self, timeout: float = 2.0) -> None:
        """Send anything buffered before the process exits."""
        ...


class _NullSpan:
    """A span that forgets everything. Used when tracing is off."""

    def set_data(self, key: str, value: int | float) -> None:  # noqa: ARG002
        return None

    def set_token_usage(self, *, input_tokens: int, output_tokens: int) -> None:  # noqa: ARG002
        return None


@contextmanager
def null_span() -> Iterator[Span]:
    """A context manager that yields a span which discards every write."""
    yield _NullSpan()


class NoOpTracer:
    """The tracer used with no DSN, or with the extra not installed.

    It is a real object rather than ``None`` so call sites have no branch to
    forget: ``tracer.span(...)`` always returns a usable context manager.
    """

    enabled = False

    @contextmanager
    def transaction(self, name: str, op: str = "pipeline") -> Iterator[None]:  # noqa: ARG002
        yield

    def span(self, op: str, description: str = "") -> AbstractContextManager[Span]:  # noqa: ARG002
        return null_span()

    def flush(self, timeout: float = 2.0) -> None:  # noqa: ARG002
        return None


__all__ = ["NoOpTracer", "Span", "Tracer", "null_span"]
