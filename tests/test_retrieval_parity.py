"""Backend parity: both retrievers must answer the same query the same way.

``RULES.md`` §6 makes this a hard invariant — the local FTS5 backend and the
Tiger Cloud hybrid backend are peers behind one ``Retriever`` interface, and a
divergence in what they return is a bug in one of them.

The cloud side needs a ``SLOTH_DATABASE_URL`` **and** the Tiger backend, which
is wired up in Phase 4; until then the parity half of this module skips with the
reason, while the local half always runs so the parity harness itself is not
dead code. This is deliberate: a parity test that silently compared an absent
backend to itself would be worse than no test at all.
"""

from __future__ import annotations

import os
import sqlite3

import pytest

from sloth_drawer.retrieval.base import ChunkRef
from sloth_drawer.retrieval.local import LocalRetriever

MANUAL_SHA = "sha-parity"

CORPUS = [
    (
        12,
        "4.2 Filter Maintenance",
        "The Pre-Carbon filter (Part No. DX-CF14) must be replaced every 2 months.",
    ),
    (13, "4.3 Exterior Care", "Wipe the exterior with a dry cloth every 2 weeks."),
    (
        14,
        "5.1 Spare Parts",
        "The HEPA filter (Part No. DX-HF22) should be replaced every 12 months.",
    ),
]

#: One identifier query and three natural-language ones — the two strengths the
#: backends are supposed to share. Every word of a query must be present: the
#: local trigram index ANDs its terms, which is exactly the behaviour the parity
#: run is checking against the cloud backend.
QUERIES = ["DX-CF14", "Pre-Carbon filter", "HEPA filter", "exterior cloth"]


def _local() -> LocalRetriever:
    retriever = LocalRetriever(sqlite3.connect(":memory:"))
    retriever.index(MANUAL_SHA, "duramax-dx900p", CORPUS)
    return retriever


def _tiger():
    """Build the cloud retriever, or skip with the reason it is unavailable."""
    if not os.environ.get("SLOTH_DATABASE_URL"):
        pytest.skip("set SLOTH_DATABASE_URL to run the backend parity check")
    try:
        from sloth_drawer.retrieval.tiger import TigerRetriever
    except ModuleNotFoundError:
        pytest.skip("the tiger backend lands in Phase 4; parity runs once it exists")
    return TigerRetriever.from_env()


def test_the_local_backend_answers_every_parity_query() -> None:
    """The harness is real: the local half of the parity check must find each query."""
    retriever = _local()
    for query in QUERIES:
        hits = retriever.search(query, k=5)
        assert hits, f"the local backend found nothing for {query!r}"
        assert all(isinstance(hit, ChunkRef) for hit in hits)


def test_a_part_number_reaches_the_expected_chunk() -> None:
    hits = _local().search("DX-CF14", k=5)
    assert hits[0].page == 12
    assert "DX-CF14" in hits[0].content


def test_both_backends_reach_the_same_chunks_over_one_corpus() -> None:
    """The invariant from RULES.md §6 — over the *real* corpus, both sides.

    A parity check against the tiny unit fixture would be comparing two corpora,
    not two backends: the cloud index holds `data/manuals`, so the local side of
    this test builds the same in-memory index `bench/parity.py` does. The
    invariant is the honest window one the bench run established — the ranks
    differ on purpose (RRF fusion vs strict-conjunctive FTS5), but every chunk
    the local window returns must be reachable from the cloud window, because a
    card cites one chunk and both backends owe that chunk.
    """
    import sys
    from pathlib import Path

    _tiger()  # skips with the reason unless the DSN is set
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from bench.parity import LOCAL_WINDOW, QUERIES, TIGER_WINDOW, build_local

    if not (root / "data" / "manuals").is_dir():
        pytest.skip("data/manuals missing; the shared-corpus parity run needs it")

    local, _note = build_local()
    tiger = _tiger()

    for query in QUERIES:
        local_hits = local.search(query, k=LOCAL_WINDOW)
        cloud_hits = tiger.search(query, k=TIGER_WINDOW)
        cloud_pages = {(hit.page, hit.content) for hit in cloud_hits}
        for hit in local_hits:
            assert (hit.page, hit.content) in cloud_pages, (
                f"for {query!r} the local hit on page {hit.page} is absent from "
                f"the cloud top-{TIGER_WINDOW}"
            )


def test_each_backend_names_itself() -> None:
    assert _local().name == "local"
    tiger = _tiger()
    assert tiger.name == "tiger"
