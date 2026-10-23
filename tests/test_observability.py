"""The tracing boundary: off by default, numeric-only when on.

Two things are worth pinning. First, the core path must not need the optional
``sentry-sdk``: with no DSN the tracer is a real no-op, never ``None`` and never
a ``ModuleNotFoundError``. Second, a span must be **unable** to carry the text
being processed — the ``Span`` protocol exposes only counts and token usage, so
the privacy boundary in RULES.md 3.1a is a property of the type rather than of
the discipline of the call sites.
"""

from __future__ import annotations

from sloth_drawer.config import Config, Paths
from sloth_drawer.observability import NoOpTracer, init_tracing, null_span
from sloth_drawer.observability.base import Span
from sloth_drawer.observability.sentry import STAGES
from sloth_drawer.pipeline import stage


def _config(tmp_path, dsn: str | None) -> Config:
    return Config(
        paths=Paths(root=tmp_path),
        ollama_host="http://127.0.0.1:11434",
        ollama_timeout=30.0,
        retrieval="local",
        database_url=None,
        embed_model="nomic-embed-text",
        embed_dims=768,
        sentry_dsn=dsn,
    )


def test_no_dsn_means_no_tracer(tmp_path) -> None:
    tracer = init_tracing(_config(tmp_path, None))
    assert isinstance(tracer, NoOpTracer)
    assert tracer.enabled is False


def test_a_dsn_without_the_extra_degrades_to_a_no_op(tmp_path) -> None:
    """sentry-sdk is an optional extra; its absence must not raise."""
    tracer = init_tracing(_config(tmp_path, "https://key@o0.ingest.sentry.io/0"))
    assert isinstance(tracer, NoOpTracer)
    assert tracer.enabled is False


def test_the_no_op_tracer_is_usable_without_a_branch() -> None:
    tracer = NoOpTracer()
    tracer.flush()
    with tracer.transaction("scan"), tracer.span("extract", "gemma3:1b") as span:
        span.set_data("chunks.candidates", 3)
        span.set_token_usage(input_tokens=10, output_tokens=4)


def test_a_stage_without_a_tracer_yields_a_usable_span() -> None:
    with stage(None, "verify", "locate -> expand") as span:
        span.set_data("verify.accepted", 1)


def test_null_span_discards_every_write() -> None:
    with null_span() as span:
        assert span.set_data("x", 1) is None
        assert span.set_token_usage(input_tokens=1, output_tokens=1) is None


def test_a_span_cannot_carry_text() -> None:
    """The only two writes are numeric. There is no ``set_text``/``set_prompt``."""
    public = {name for name in dir(Span) if not name.startswith("_")}
    assert public == {"set_data", "set_token_usage"}


def test_the_stage_vocabulary_is_one_per_pipeline_step() -> None:
    assert STAGES == ("ingest", "chunk", "prefilter", "triage", "extract", "verify", "persist")
