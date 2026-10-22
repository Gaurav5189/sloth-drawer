"""Typed exceptions and exit codes.

Every exception this project raises lives here and subclasses :class:`SlothDrawerError`.
Library code never raises a bare ``ValueError``/``RuntimeError``, because a caller
cannot then tell "the model returned junk" from "the database is gone" without
matching on message text (RULES.md 2.2).

Two distinctions matter more than the rest:

*   A **REJECT verdict is not an exception.** It is a successful run with a bad
    outcome. A batch of 12 manuals where 3 intervals were rejected must exit
    1 with warnings, not raise.
*   **Every failure is a recorded outcome.** An unreadable PDF, a model
    timeout, a rejected interval — each becomes a row in the report with a
    reason code, never a crash that aborts the batch.
"""

from __future__ import annotations

# Exit codes (RULES.md 2.5).
EXIT_OK = 0
EXIT_PARTIAL = 1
EXIT_FATAL = 2
EXIT_INTERRUPTED = 130


class SlothDrawerError(Exception):
    """Base class for every error raised by this project.

    ``exit_code`` says how the CLI should terminate. Subclasses that represent a
    *configuration* problem fail fast with :data:`EXIT_FATAL`; subclasses that
    represent a *content* problem are caught by the batch runner and recorded.
    """

    exit_code = EXIT_FATAL
    #: Stable machine-readable code, used in reports and logs.
    reason: str = "error"


class ConfigError(SlothDrawerError):
    """Bad configuration, missing files, or an unusable model id.

    Fail fast: nothing is written when this is raised.
    """


class CorpusError(SlothDrawerError):
    """A manual could not be read.

    ``reason`` distinguishes the skippable cases: ``no_text_layer``,
    ``encrypted_pdf``, ``corrupt_pdf``, ``empty_pdf``.
    """

    def __init__(self, message: str, reason: str = "corpus_error") -> None:
        super().__init__(message)
        self.reason = reason


class NoTextLayerError(CorpusError):
    """Image-only PDF: there is nothing to extract, so the file is skipped."""

    def __init__(self, message: str) -> None:
        super().__init__(message, reason="no_text_layer")


class ModelError(SlothDrawerError):
    """Something went wrong talking to the local model."""


class OllamaUnavailableError(ModelError):
    """The Ollama server cannot be reached.

    Fail fast and do not retry: if the server is not there, it will not be there
    in two seconds either.
    """


class ModelTimeoutError(ModelError):
    """A single model call exceeded its timeout."""


class ModelSchemaError(ModelError):
    """The response was not valid JSON, or did not match the requested schema."""


class ModelOutputError(ModelError):
    """The response was valid JSON but semantically unusable (e.g. an empty array)."""


class VerificationError(SlothDrawerError):
    """The verifier itself could not run.

    Never raised for a REJECT — a rejected candidate is a result, not a failure.
    """


class StorageError(SlothDrawerError):
    """A SQLite problem: the database is missing, locked, or corrupt."""
