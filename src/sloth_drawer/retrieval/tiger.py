"""The cloud retrieval backend: pgvector + pg_textsearch, fused with RRF.

Two queries run in parallel — a vector arm (semantic paraphrases the keyword
index misses) and a BM25 arm (rare words and identifiers the embeddings
flatten) — and Reciprocal Rank Fusion merges *ranks*, not scores, with
``k = 60`` from the Cormack–Clarke–Buettcher paper. BM25 scores are negative
and lower is better; they are never normalised and never compared with a
cosine similarity, because that comparison is meaningless and RRF exists
precisely so it never has to happen (RULES.md 1.3).

The four traps measured against the live service on 2026-10-22 are encoded
here as structure, not comments: the two-argument ``to_bm25query`` with a
schema-qualified index name (always), the bare-overload trap (never), an
unqualified index name in ``CREATE INDEX`` (schema.sql's job), and ranks-not-
scores (this query's job).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import psycopg
from pgvector.psycopg import register_vector

from sloth_drawer.errors import ConfigError
from sloth_drawer.retrieval.base import ChunkRef

if TYPE_CHECKING:  # pragma: no cover - only the type checker pulls this in
    from sloth_drawer.config import Config

#: RRF constant ``k``. From the Cormack–Clarke–Buettcher paper; not tuned.
RRF_K = 60

#: The schema-qualified index name. An unqualified name fails with
#: ``index "..." does not exist`` unless search_path already contains sloth.
BM25_INDEX = "sloth.manual_chunks_bm25_idx"

#: How deep each arm reaches before the fusion. Deep enough that a perfect
#: chunk ranked 15th by one arm can still surface top-5 fused.
ARM_DEPTH = 20

HYBRID_SQL = f"""\
WITH vec AS (
  SELECT id, ROW_NUMBER() OVER (ORDER BY embedding <=> %s::vector) AS rank
  FROM sloth.manual_chunks ORDER BY embedding <=> %s::vector LIMIT {ARM_DEPTH}
), kw AS (
  SELECT id, ROW_NUMBER() OVER (ORDER BY content <@> to_bm25query(%s,'{BM25_INDEX}')) AS rank
  FROM sloth.manual_chunks
  ORDER BY content <@> to_bm25query(%s,'{BM25_INDEX}') LIMIT {ARM_DEPTH}
)
SELECT m.manual_sha, m.device_slug, m.page, m.section, m.content,
       COALESCE(1.0/({RRF_K}+v.rank),0) + COALESCE(1.0/({RRF_K}+k.rank),0) AS score
FROM sloth.manual_chunks m
LEFT JOIN vec v ON v.id = m.id
LEFT JOIN kw  k ON k.id = m.id
WHERE v.id IS NOT NULL OR k.id IS NOT NULL
ORDER BY score DESC LIMIT %s
"""


class TigerRetriever:
    """Search the hybrid index on Tiger Cloud. The write path lives in
    ``vector/indexer.py``; this class only queries, so the interface stays
    exactly what ``Retriever`` asks for."""

    name = "tiger"

    def __init__(
        self,
        connection: psycopg.Connection,
        *,
        embed_query: Callable[[str], list[float]],
        dsn_redacted: str = "the configured service",
    ) -> None:
        self._connection = connection
        self._embed_query = embed_query
        self._dsn_redacted = dsn_redacted

    @classmethod
    def from_env(cls, config: Config | None = None) -> TigerRetriever:
        """Build the retriever from configuration, failing fast on a bad DSN.

        No DSN is not an error by itself (RULES.md 2.4a: unset means the local
        backend) — but asking *this* class for a retriever without one is,
        because the local backend should be selected by config, never reached
        by falling out of a cloud constructor.
        """
        dsn = getattr(config, "database_url", None)
        if not dsn:
            import os

            dsn = os.environ.get("SLOTH_DATABASE_URL", "").strip()
        if not dsn:
            raise ConfigError(
                "Tiger retriever needs SLOTH_DATABASE_URL. Without it the local "
                "SQLite FTS5 backend is selected automatically — nothing to set "
                "up, and no network."
            )
        try:
            connection = psycopg.connect(dsn)
        except Exception as exc:  # noqa: BLE001 - psycopg raises many families
            redacted = (
                getattr(config, "redacted_database_url", "")
                if config is not None
                else cls._redact_none(dsn)
            )
            raise ConfigError(
                f"Cannot reach Tiger Cloud at {redacted}. Check the DSN and that "
                "the service is running. To run fully offline, unset "
                "SLOTH_DATABASE_URL."
            ) from exc

        if config is not None and getattr(config, "embed_dims", None):
            embed_query = cls._embedder(
                embed_model=config.embed_model,
                embed_dims=config.embed_dims,
                ollama_host=config.ollama_host,
            )
        else:
            import os

            embed_query = cls._embedder(
                embed_model=os.environ.get("SLOTH_EMBED_MODEL", "").strip() or "nomic-embed-text",
                embed_dims=int(os.environ.get("SLOTH_EMBED_DIMS", "768") or 768),
                ollama_host=os.environ.get("SLOTH_OLLAMA_HOST", "").strip()
                or "http://localhost:11434",
            )

        register_vector(connection)
        return cls(
            connection, embed_query=embed_query, dsn_redacted=TigerRetriever._redact_none(dsn)
        )

    @staticmethod
    def _redact_none(dsn: str) -> str:
        """Mask the DSN's password without importing the config module."""
        from sloth_drawer.config import redact_dsn

        return redact_dsn(dsn)

    @classmethod
    def _embedder(
        cls, *, embed_model: str, embed_dims: int, ollama_host: str
    ) -> Callable[[str], list[float]]:
        """A one-query embedding function with the dimension check baked in.

        A dimension mismatch is a startup error (RULES.md 1.4), raised the
        first time it can be observed, not a runtime surprise mid-corpus.
        """
        from sloth_drawer.extract.embed import embed

        def embed_one(query: str) -> list[float]:
            (vector,) = embed([query], model=embed_model, host=ollama_host).vectors
            if len(vector) != embed_dims:
                raise ConfigError(
                    f"The embedding model {embed_model!r} returned {len(vector)} "
                    f"dimensions but the manual_chunks column expects {embed_dims}. "
                    "Set SLOTH_EMBED_DIMS to match, or point SLOTH_EMBED_MODEL at "
                    "the model the column was built for."
                )
            return vector

        return embed_one

    def search(self, query: str, k: int) -> list[ChunkRef]:
        """One hybrid query: embed, fuse the two arms, return ranked chunks."""
        vector = self._embed_query(query)
        try:
            rows = self._connection.execute(
                HYBRID_SQL, (vector, vector, query, query, k)
            ).fetchall()
        except psycopg.Error as exc:
            message = str(exc)
            if "to_bm25query" in message and "does not exist" in message:
                raise ConfigError(
                    "The pg_textsearch extension is not available on this service "
                    "(it needs PostgreSQL 17/18). To run fully offline, unset "
                    "SLOTH_DATABASE_URL."
                ) from exc
            if "dimensions" in message:
                raise ConfigError(
                    f"The query embedding does not match the stored vectors on "
                    f"{self._dsn_redacted}: {message.strip()[:300]}. Rebuild the "
                    "index or change SLOTH_EMBED_MODEL — both sides must use the "
                    "same model and width."
                ) from exc
            raise ConfigError(f"The Tiger Cloud search failed: {message.strip()[:300]}") from exc

        return [
            ChunkRef(
                manual_sha=str(row[0]),
                page=int(row[2]),
                section=row[3],
                content=str(row[4]),
                score=float(row[5]),
                backend=self.name,
            )
            for row in rows
        ]


__all__ = ["ARM_DEPTH", "BM25_INDEX", "HYBRID_SQL", "RRF_K", "TigerRetriever"]
