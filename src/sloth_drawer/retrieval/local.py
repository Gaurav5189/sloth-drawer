"""The local retrieval backend: SQLite FTS5 with the trigram tokenizer.

This is the default. It needs no configuration, no network and no account, and
it works with the Wi-Fi off — which is a release gate, not a nicety
(RULES.md 2.4a, C14).

The ``trigram`` tokenizer is the reason this backend is a peer rather than a
downgrade. A word tokenizer splits ``DX-CF14`` into pieces and throws the
identifier away; a trigram index matches it exactly. That is the same blind
spot the BM25 arm of the cloud backend covers, which is why the two are
comparable rather than one being the fallback for the other.

The score is SQLite's ``bm25()``: **negative, lower is better**. It is not
normalised and it is not comparable with the cloud backend's fused score.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from sloth_drawer.errors import StorageError
from sloth_drawer.retrieval.base import ChunkRef

#: The FTS5 table. ``trigram`` is the point of this backend.
SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
  content,
  manual_sha UNINDEXED,
  device_slug UNINDEXED,
  page UNINDEXED,
  section UNINDEXED,
  tokenize='trigram'
);
"""

#: The trigram tokenizer needs three characters to match anything.
MIN_QUERY_CHARS = 3


def _match_expression(query: str) -> str:
    """Turn a plain-text query into an FTS5 expression.

    Each word becomes a quoted phrase. Unquoted, a part number such as
    ``DX-CF14`` is parsed by FTS5 as a column filter and the query dies with
    "no such column: CF14" — which is exactly the identifier this backend
    exists to find. Quotes make every word a literal.
    """
    words = [word for word in query.replace('"', " ").split() if len(word) >= MIN_QUERY_CHARS]
    if not words:
        return ""
    return " AND ".join(f'"{word}"' for word in words)


class LocalRetriever:
    """A local FTS5 index over manual chunks."""

    name = "local"

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        try:
            self._connection.execute(SCHEMA)
        except sqlite3.Error as exc:
            raise StorageError(f"Could not create the local search index: {exc}") from exc

    def index(
        self,
        manual_sha: str,
        device_slug: str,
        chunks: list[tuple[int, str | None, str]],
    ) -> int:
        """Add chunks to the index. Returns how many rows were written."""
        rows = [
            (content, manual_sha, device_slug, page, section) for page, section, content in chunks
        ]
        if not rows:
            return 0
        try:
            self._connection.executemany(
                "INSERT INTO chunk_fts (content, manual_sha, device_slug, page, section) "
                "VALUES (?, ?, ?, ?, ?)",
                rows,
            )
        except sqlite3.Error as exc:
            raise StorageError(f"Could not index the chunks: {exc}") from exc
        return len(rows)

    def search(self, query: str, k: int) -> list[ChunkRef]:
        """Find the chunks most relevant to a query.

        A query shorter than three characters cannot match a trigram, so it
        returns nothing rather than erroring.
        """
        match = _match_expression(query)
        if not match:
            return []

        try:
            rows = self._connection.execute(
                "SELECT manual_sha, page, section, content, bm25(chunk_fts) AS score "
                "FROM chunk_fts WHERE chunk_fts MATCH ? ORDER BY score LIMIT ?",
                (match, k),
            ).fetchall()
        except sqlite3.Error as exc:
            raise StorageError(f"The local search failed: {exc}") from exc

        return [
            ChunkRef(
                manual_sha=manual_sha,
                page=int(page),
                section=section,
                content=content,
                score=float(score),
                backend=self.name,
            )
            for manual_sha, page, section, content, score in rows
        ]

    @classmethod
    def open(cls, db_path: Path) -> LocalRetriever:
        """Open (and create) a local index at ``db_path``."""
        try:
            connection = sqlite3.connect(str(db_path))
        except sqlite3.Error as exc:
            raise StorageError(f"Could not open the local database at {db_path}: {exc}") from exc
        connection.row_factory = sqlite3.Row
        return cls(connection)
