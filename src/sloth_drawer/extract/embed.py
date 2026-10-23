"""Embeddings from the same local Ollama that runs the extractor.

The embedder is a *sensor*, like the extractor: it turns chunk text into
vectors and nothing else. Vectors go to Tiger Cloud (RULES.md 3.1a); nothing
identifying the user's home goes with them, because this module only ever
receives chunk text — the same text the code quotes and verifies.

The request goes through the same stdlib client as generate; embeddings are
batched because a manual yields hundreds of chunks and a per-chunk queue would
spend the run in HTTP overhead rather than inference.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass

from sloth_drawer.extract.ollama import (
    DEFAULT_TIMEOUT,
    EMBED_PATH,
    OllamaUnavailableError,
    post_json,
)

#: How many texts go into one /api/embed call. Small enough to keep a 4-core
#: box responsive, large enough that HTTP overhead stays invisible.
BATCH_TEXTS = 32


@dataclass(frozen=True)
class Embeddings:
    """One batched embedding reply, in the order the texts were given."""

    vectors: list[list[float]]
    elapsed: float


def embed(
    texts: Sequence[str],
    *,
    model: str,
    host: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> Embeddings:
    """Embed ``texts`` in batches and return one vector per text, in order."""
    if not texts:
        return Embeddings(vectors=[], elapsed=0.0)

    started = time.monotonic()
    vectors: list[list[float]] = []
    for start in range(0, len(texts), BATCH_TEXTS):
        batch = list(texts[start : start + BATCH_TEXTS])
        payload = {"model": model, "input": batch}
        document, _ = post_json(host, EMBED_PATH, payload, timeout)
        returned = document.get("embeddings")
        if (
            not isinstance(returned, list)
            or len(returned) != len(batch)
            or not all(isinstance(row, list) and row for row in returned)
        ):
            raise OllamaUnavailableError(
                f"Ollama did not return {len(batch)} embedding(s) for {model}."
            )
        vectors.extend([[float(value) for value in row] for row in returned])

    return Embeddings(vectors=vectors, elapsed=time.monotonic() - started)


__all__ = ["BATCH_TEXTS", "Embeddings", "embed"]
