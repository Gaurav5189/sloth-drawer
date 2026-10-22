"""Tests for the typed exception hierarchy (RULES.md 2.2)."""

from __future__ import annotations

import pytest

from sloth_drawer.errors import (
    EXIT_FATAL,
    EXIT_INTERRUPTED,
    EXIT_OK,
    EXIT_PARTIAL,
    ConfigError,
    CorpusError,
    ModelError,
    ModelOutputError,
    ModelSchemaError,
    ModelTimeoutError,
    NoTextLayerError,
    OllamaUnavailableError,
    SlothDrawerError,
    StorageError,
    VerificationError,
)


def test_every_error_subclasses_the_base() -> None:
    for error in (
        ConfigError,
        CorpusError,
        ModelError,
        VerificationError,
        StorageError,
    ):
        assert issubclass(error, SlothDrawerError)


def test_hierarchy_matches_the_documented_tree() -> None:
    assert issubclass(NoTextLayerError, CorpusError)
    assert issubclass(OllamaUnavailableError, ModelError)
    assert issubclass(ModelTimeoutError, ModelError)
    assert issubclass(ModelSchemaError, ModelError)
    assert issubclass(ModelOutputError, ModelError)


def test_exit_codes_are_stable() -> None:
    assert (EXIT_OK, EXIT_PARTIAL, EXIT_FATAL, EXIT_INTERRUPTED) == (0, 1, 2, 130)
    assert SlothDrawerError.exit_code == EXIT_FATAL


def test_no_text_layer_carries_its_reason_code() -> None:
    error = NoTextLayerError("no extractable text")
    assert error.reason == "no_text_layer"
    assert "no extractable text" in str(error)


def test_corpus_error_reason_is_overridable() -> None:
    assert CorpusError("boom", reason="corrupt_pdf").reason == "corrupt_pdf"
    assert CorpusError("boom").reason == "corpus_error"


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (ConfigError("bad"), "bad"),
        (StorageError("locked"), "locked"),
        (VerificationError("no source"), "no source"),
    ],
)
def test_messages_survive(error: SlothDrawerError, message: str) -> None:
    assert str(error) == message


def test_a_reject_is_not_an_exception() -> None:
    """A rejected candidate is a result, so no error type models it."""
    assert not any(
        issubclass(error, SlothDrawerError) and "Reject" in error.__name__
        for error in (
            ConfigError,
            CorpusError,
            ModelError,
            VerificationError,
            StorageError,
        )
    )
