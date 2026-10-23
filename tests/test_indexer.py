"""The cloud indexer: schema, per-chunk failure recording, and the boundary.

The interesting failures here are the ones RULES.md 2.4a pins down: an embed
failure is a recorded ``embed_failed``, an upsert failure is a recorded
``index_failed``, and neither aborts the manual. The boundary itself — that
the writer cannot even see a device name it was not handed — is already
enforced where imports are checked (``tests/test_import_direction.py``), so
these tests check the *behaviour*.
"""

from __future__ import annotations

import pytest

from sloth_drawer.errors import ConfigError
from sloth_drawer.vector.indexer import SCHEMA_PATH, CloudIndex

CHUNKS = [
    (12, "4.2 Filter Maintenance", "Replace the Pre-Carbon filter every 2 months."),
    (12, "4.2 Filter Maintenance", "Clean the dust sensor every month."),
    (13, "4.3 Exterior Care", "Wipe the exterior with a dry cloth every 2 weeks."),
]


class FakeConnection:
    """Enough of psycopg for the write path; failures are injected per row."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple | None]] = []
        self.fail_on: set[str] = set()
        self.commits = 0
        self.rollbacks = 0

    def _key_of(self, sql: str, params: tuple | None) -> str:
        # Upserts carry the chunk content in params[4]; the schema statement
        # carries everything in the SQL text itself.
        return params[4] if params is not None and len(params) > 4 else sql

    def execute(self, sql, params=None):
        key = self._key_of(sql, params)
        if any(marker in key for marker in self.fail_on):
            import psycopg

            raise psycopg.OperationalError("injected failure")
        self.executed.append((sql, params))
        return "cursor"

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _cloud(connection, embed) -> CloudIndex:
    return CloudIndex(
        connection,
        embed_model="nomic-embed-text",
        embed_dims=768,
        dsn_redacted="postgres://app:***@tiger",
        embed_query=embed,
    )


def _fake_embed_fail_on(texts_that_fail: set[str]):
    def embed_batch(texts):
        rows = []
        for text in texts:
            if text in texts_that_fail:
                raise RuntimeError("embed boom")
            rows.append([0.0] * 768)
        return rows

    return embed_batch


def test_the_schema_carries_the_boundary_and_the_measured_rules() -> None:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    columns_sql = sql.lower().split("create table")[1].split(")")[0]
    for banned in ("device_name", "partial", "purchase", "serial_", "service_event", "owner"):
        assert banned not in columns_sql, banned
    for required in (
        "CREATE SCHEMA IF NOT EXISTS sloth",
        "vector(768)",
        "text_config='english'",
        "ON manual_chunks USING bm25(content)",
    ):
        assert required in sql
    statements = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    assert "CREATE INDEX sloth." not in statements, "CREATE INDEX takes an unqualified name"


def test_every_chunk_is_upserted_with_its_embedding() -> None:
    connection = FakeConnection()
    counts = _cloud(connection, _fake_embed_fail_on(set())).index_manual("sha", "slug", CHUNKS)
    assert counts == {"indexed": 3, "embed_failed": 0, "index_failed": 0}
    upserts = [params for sql, params in connection.executed if params is not None]
    assert len(upserts) == 3
    assert {params[0] for params in upserts} == {"slug"}
    assert {params[1] for params in upserts} == {"sha"}
    assert all(len(params[5]) == 768 for params in upserts)


def test_an_embed_failure_is_recorded_and_the_manual_continues() -> None:
    connection = FakeConnection()
    counts = _cloud(connection, _fake_embed_fail_on({CHUNKS[1][2]})).index_manual(
        "sha", "slug", CHUNKS
    )
    assert counts == {"indexed": 2, "embed_failed": 1, "index_failed": 0}


def test_an_upsert_failure_is_recorded_and_rolled_back() -> None:
    connection = FakeConnection()
    connection.fail_on = {CHUNKS[1][2]}
    counts = _cloud(connection, _fake_embed_fail_on(set())).index_manual("sha", "slug", CHUNKS)
    assert counts == {"indexed": 2, "embed_failed": 0, "index_failed": 1}
    assert connection.rollbacks == 1


def test_a_dimension_mismatch_is_a_config_error_named_on_both_sides() -> None:
    def wrong_dims(texts):
        return [[0.0] * 512 for _ in texts]

    with pytest.raises(ConfigError) as caught:
        _cloud(FakeConnection(), wrong_dims).index_manual("sha", "slug", CHUNKS)
    message = str(caught.value)
    assert "512" in message and "768" in message and "SLOTH_EMBED_DIMS" in message


def test_every_embed_failure_is_recorded_when_the_model_is_down() -> None:
    connection = FakeConnection()
    counts = _cloud(connection, _fake_embed_fail_on({chunk[2] for chunk in CHUNKS})).index_manual(
        "sha", "slug", CHUNKS
    )
    assert counts == {"indexed": 0, "embed_failed": 3, "index_failed": 0}
