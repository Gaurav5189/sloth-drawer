"""The Tiger retriever, without a live service.

Everything that can break on a datasheet-postgres can be pinned down against a
fake connection: the SQL text (the four measured traps), the typed mapping of
service errors, and the no-DSNContract behaviour. The live parity run against
real Tiger Cloud is ``bench/parity.py`` plus ``tests/test_retrieval_parity.py``.
"""

from __future__ import annotations

import pytest

from sloth_drawer.errors import ConfigError
from sloth_drawer.retrieval.tiger import BM25_INDEX, HYBRID_SQL, RRF_K, TigerRetriever


def test_hybrid_sql_uses_the_two_arg_schema_qualified_bm25() -> None:
    """The one-argument overload is a trap with a typed argument; never used."""
    assert HYBRID_SQL.count("to_bm25query(%s," + f"'{BM25_INDEX}')") == 2, (
        "the to_bm25query call belongs in both the window function and the ORDER BY"
    )
    assert BM25_INDEX.startswith("sloth."), "the index name must be schema-qualified"
    assert "'{RRF_K}'" not in HYBRID_SQL


def test_rrf_fuses_ranks_not_scores() -> None:
    """Negative BM25 scores are never normalised against cosine similarity."""
    assert "ORDER BY embedding <=> %s::vector" in HYBRID_SQL
    assert f"1.0/({RRF_K}+" in HYBRID_SQL
    assert "<@>" in HYBRID_SQL


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeConnection:
    """Just enough psycopg for the query path."""

    def __init__(self, rows=(), error: Exception | None = None):
        self.rows = rows
        self.error = error
        self.params: tuple = ()

    def execute(self, sql, params):
        assert sql, "the hybrid query is never empty"
        self.params = params
        if self.error is not None:
            raise self.error
        return FakeCursor(self.rows)


def _retriever(connection) -> TigerRetriever:
    return TigerRetriever(connection, embed_query=lambda _text: [0.1, 0.2, 0.3])


ROWS = [
    (
        "sha-1",
        "duramax-dx900p",
        12,
        "4.2 Filter Maintenance",
        "text every 2 months",
        1.0 / (60 + 1),
    ),
]


def test_search_maps_rows_to_chunk_refs_with_the_backend_named() -> None:
    retriever = _retriever(FakeConnection(ROWS))
    [hit] = retriever.search("Pre-Carbon filter", k=5)
    assert hit.backend == "tiger"
    assert hit.page == 12
    assert hit.score > 0  # a fused rank score, never a negative BM25 score


def test_search_sends_the_vector_twice_and_the_query_twice() -> None:
    connection = FakeConnection(ROWS)
    retriever = _retriever(connection)
    retriever.search("DX-CF14", k=7)
    vector, vector_again, query, query_again, k = connection.params
    assert vector == [0.1, 0.2, 0.3] and vector_again == vector
    assert query == "DX-CF14" and query_again == query
    assert k == 7


def test_a_missing_extension_is_a_config_error_with_the_remediation() -> None:
    import psycopg

    conn = FakeConnection(
        error=psycopg.errors.UndefinedFunction("function to_bm25query(unknown) does not exist")
    )
    with pytest.raises(ConfigError) as caught:
        _retriever(conn).search("q", 5)
    assert "pg_textsearch" in str(caught.value)
    assert "SLOTH_DATABASE_URL" in str(caught.value)


def test_a_dimension_mismatch_names_the_fix() -> None:
    import psycopg

    conn = FakeConnection(error=psycopg.errors.DataError("expected 768 dimensions, not 512"))
    with pytest.raises(ConfigError) as caught:
        _retriever(conn).search("q", 5)
    assert "SLOTH_EMBED_MODEL" in str(caught.value)


def test_from_env_without_a_dsn_says_what_to_do(monkeypatch) -> None:
    monkeypatch.delenv("SLOTH_DATABASE_URL", raising=False)
    with pytest.raises(ConfigError) as caught:
        TigerRetriever.from_env()
    assert "SLOTH_DATABASE_URL" in str(caught.value)
    assert "local" in str(caught.value)
