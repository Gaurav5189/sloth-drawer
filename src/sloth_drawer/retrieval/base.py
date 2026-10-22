"""The retrieval interface: one method, two backends.

The whole point of this module is that it is small. ``Retriever.search`` is the
only public operation, and the pipeline never asks which backend it is talking
to (RULES.md 6).

Both backends must produce the **same card for the same manual**. A divergence
is a bug in one of them, and the parity run in Phase 3 is what proves it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ChunkRef:
    """One retrievable chunk, with enough context to cite it.

    ``score`` is the backend's own relevance score. The local backend uses
    SQLite's ``bm25()`` and the cloud backend uses fused RRF ranks; they are
    **not** comparable with each other and are never compared (RULES.md 2.4a).
    """

    manual_sha: str
    page: int
    section: str | None
    content: str
    score: float
    backend: str


@runtime_checkable
class Retriever(Protocol):
    """What the pipeline asks of a backend."""

    name: str

    def search(self, query: str, k: int) -> list[ChunkRef]:
        """Return the ``k`` chunks most relevant to ``query``."""
        ...
