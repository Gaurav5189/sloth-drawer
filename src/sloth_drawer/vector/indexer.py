"""The write path to Tiger Cloud: chunk -> nomic-embed-text -> upsert.

This module is the whole cloud boundary (RULES.md 3.1a) made concrete. It
receives **chunk text only**: the caller hands it tuples of
``(page, section, content)`` plus a with-hash and a generic slug. It cannot
import ``sloth_drawer.storage``, so the device registry, the serial numbers
and the service log are physically out of its reach — the privacy rule is a
dependency rule, not a promise in a comment.

Every failure below a whole-connection failure is a recorded outcome, never a
crash (RULES.md 2.4a): one chunk that fails to embed becomes ``embed_failed``
and the manual continues; the local backend does not even notice.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

import psycopg
from pgvector.psycopg import register_vector

from sloth_drawer.errors import ConfigError, OllamaUnavailableError

if TYPE_CHECKING:  # pragma: no cover - the config shape is structural only
    from collections.abc import Callable, Sequence

LOGGER = logging.getLogger("sloth_drawer.vector")

#: How many chunk texts go into one embedding call (mirrors extract.embed).
BATCH_TEXTS = 32

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class ConfigLike(Protocol):
    """The attributes of ``config.Config`` this module uses, and nothing more.

    A structural protocol instead of an import keeps the ``vector`` package's
    allowed-import set tiny (RULES.md 3.1a): no import of ``config`` means no
    accidental path from the cloud writer to any other module.
    """

    @property
    def database_url(self) -> str | None:
        """The raw DSN, or ``None`` with no cloud service configured."""
        ...

    @property
    def redacted_database_url(self) -> str:
        """The DSN with its password masked (RULES.md 2.4c)."""
        ...

    @property
    def embed_model(self) -> str:
        """The Ollama model producing chunk embeddings."""
        ...

    @property
    def embed_dims(self) -> int:
        """The vector width `manual_chunks` was built for."""
        ...

    @property
    def ollama_host(self) -> str:
        """The local Ollama base URL."""
        ...


class IndexableManual(Protocol):
    """The shape the index writer accepts: a manual's chunks without identity."""

    manual_sha: str
    device_slug: str


class CloudIndex:
    """The ``manual_chunks`` table on a Tiger Cloud (or any Postgres) service."""

    name = "tiger"

    def __init__(
        self,
        connection: psycopg.Connection,
        *,
        embed_model: str,
        embed_dims: int,
        dsn_redacted: str,
        embed_query: Callable[[Sequence[str]], list[list[float]]],
    ) -> None:
        self._connection = connection
        self._embed_model = embed_model
        self._embed_dims = embed_dims
        self._dsn_redacted = dsn_redacted
        self._embed_query = embed_query

    @classmethod
    def from_env(cls, config: ConfigLike) -> CloudIndex:
        """Connect, register pgvector and apply the schema, failing fast.

        An unreachable service or a missing extension is a configuration
        problem (RULES.md 2.4a): exit 2 with the exact remediation. It is
        *never* a silent fall back to the local backend — a silent fallback
        means the user thinks they queried the index and did not.
        """
        dsn = getattr(config, "database_url", None)
        if not dsn:
            raise ConfigError(
                "Cloud indexing needs SLOTH_DATABASE_URL. Unset means the local "
                "SQLite FTS5 backend, which is the default and needs nothing."
            )
        try:
            connection = psycopg.connect(str(dsn))
        except Exception as exc:  # noqa: BLE001 - psycopg raises many families
            raise ConfigError(
                f"Cannot reach Tiger Cloud at {config.redacted_database_url}. "
                "Check the DSN and that the service is running. To run fully "
                "offline, unset SLOTH_DATABASE_URL."
            ) from exc
        register_vector(connection)
        cloud = cls(
            connection,
            embed_model=config.embed_model,
            embed_dims=config.embed_dims,
            dsn_redacted=config.redacted_database_url,
            embed_query=cls._make_embedder(config),
        )
        cloud.ensure_schema()
        return cloud

    @classmethod
    def _make_embedder(cls, config: ConfigLike) -> Callable[[Sequence[str]], list[list[float]]]:
        """A batched embedding function bound to this run's embedder config.

        The import from ``extract.embed`` is deliberately lazy: ``vector`` may
        depend on ``extract.embed`` as data, but it must not drag the whole
        extractor into the module graph (ARCHITECTURE.md 3).
        """
        from sloth_drawer.extract.embed import embed

        def embed_batch(texts: Sequence[str]) -> list[list[float]]:
            return embed(texts, model=config.embed_model, host=config.ollama_host).vectors

        return embed_batch

    def ensure_schema(self) -> None:
        """Apply ``vector/schema.sql`` idempotently, with the remediation named."""
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        try:
            self._connection.execute(sql)
            self._connection.commit()
        except psycopg.Error as exc:
            message = str(exc)
            if "pg_textsearch" in message or "to_bm25query" in message:
                hint = (
                    "The pg_textsearch extension is not available on this service "
                    "(it needs PostgreSQL 17/18). To run fully offline, unset "
                    "SLOTH_DATABASE_URL."
                )
            elif "vectorscale" in message or "vector" in message:
                hint = "Run: CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE;"
            else:
                hint = "Check the service's permissions and PostgreSQL version."
            raise ConfigError(
                f"Could not apply the index schema on {self._dsn_redacted}: "
                f"{message.strip()[:400]}. {hint}"
            ) from exc

    def index_manual(
        self,
        manual_sha: str,
        device_slug: str,
        chunks: Sequence[tuple[int, str | None, str]],
    ) -> dict[str, int]:
        """Embed and upsert one manual's chunks. Returns the outcome tally.

        Chunk text and its embedding are the only things that cross the wire
        (RULES.md 3.1a). Embedding runs in batches — a manual of a few hundred
        chunks is minutes of HTTP overhead one call at a time — and a failed
        batch falls back to per-chunk calls so one poisoned chunk is recorded
        as ``embed_failed`` without losing its batch-mates. An unavailable
        embed server fails fast (RULES.md 2.3): recording 300 failures that
        are one outage would be lying in the report.
        """
        indexed = 0
        embed_failed = 0
        index_failed = 0
        for start in range(0, len(chunks), BATCH_TEXTS):
            group = chunks[start : start + BATCH_TEXTS]
            try:
                vectors: list[list[float] | None] = cast(
                    "list[list[float] | None]",
                    self._embed_query([content for _, _, content in group]),
                )
            except OllamaUnavailableError:
                raise
            except Exception:  # noqa: BLE001 - one bad chunk must not sink 31 good ones
                LOGGER.warning(
                    "a batch of %d chunk(s) failed to embed; isolating one by one", len(group)
                )
                vectors = []
                for _, _, content in group:
                    try:
                        vectors.append(self._embed_query([content])[0])
                    except OllamaUnavailableError:
                        raise
                    except Exception:  # noqa: BLE001 - recorded per chunk below
                        embed_failed += 1
                        vectors.append(None)
            for (page, section, content), vector in zip(group, vectors, strict=False):
                if vector is None:
                    continue
                if len(vector) != self._embed_dims:
                    raise ConfigError(
                        f"The embedding model {self._embed_model!r} returned "
                        f"{len(vector)} dimensions but the manual_chunks column expects "
                        f"{self._embed_dims}. Set SLOTH_EMBED_DIMS to match, or point "
                        "SLOTH_EMBED_MODEL at the model the column was built for."
                    )
                try:
                    self._connection.execute(
                        "INSERT INTO sloth.manual_chunks "
                        "(device_slug, manual_sha, page, section, content, embedding) "
                        "VALUES (%s, %s, %s, %s, %s, %s) "
                        "ON CONFLICT (manual_sha, page, content) "
                        "DO UPDATE SET embedding = EXCLUDED.embedding",
                        (device_slug, manual_sha, page, section, content, vector),
                    )
                    self._connection.commit()
                    indexed += 1
                except psycopg.Error:
                    self._connection.rollback()
                    index_failed += 1
        return {
            "indexed": indexed,
            "embed_failed": embed_failed,
            "index_failed": index_failed,
        }

    def index_chunks(
        self,
        manual_sha: str,
        device_slug: str,
        chunks: Sequence[tuple[int, str | None, str]],
    ) -> dict[str, int]:
        """The shared name both backends answer (see ``LocalRetriever``)."""
        return self.index_manual(manual_sha, device_slug, chunks)

    def chunks_for_manual(self, manual_sha: str) -> int:
        """How many of a manual's chunks are in the index (for progress lines)."""
        row = self._connection.execute(
            "SELECT count(*) FROM sloth.manual_chunks WHERE manual_sha = %s", (manual_sha,)
        ).fetchone()
        return int(row[0]) if row else 0

    def close(self) -> None:
        """Drop the connection; the local backend needs nothing like this."""
        self._connection.close()
