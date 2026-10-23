"""Backend parity diff: the run `RULES.md §6` asks for.

Phase 3 deferred this deliberately: it compares the local FTS5 backend against
the Tiger Cloud hybrid backend, and the Tiger backend did not exist yet. It is
runnable once both exist:

    # one-time per side
    uv run sloth-drawer index data/manuals                        # local
    SLOTH_DATABASE_URL=... uv run sloth-drawer index data/manuals  # cloud

    # the diff (cloud side needs the DSN; local always runs)
    SLOTH_DATABASE_URL=... uv run python bench/parity.py

The invariant checked per query is the card-shape one: the local backend's top
hit must appear in the cloud backend's top-k. Rank *within* the two top-5s may
differ — the fusion is deliberately different — but the chunk a card would
point at must be present in both.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

logging.basicConfig(level=logging.WARNING)
logging.getLogger("pypdf").setLevel(logging.ERROR)

from sloth_drawer.corpus.chunk import chunk_manual  # noqa: E402
from sloth_drawer.corpus.ingest import list_pdfs, read_manual, sha256_of, slug_from_filename  # noqa: E402
from sloth_drawer.retrieval.local import LocalRetriever  # noqa: E402

#: The local index is built in memory from the corpus, so the local side never
#: depends on whatever state out/ happens to hold. Cheap: 19 PDFs, no model.
DIRECTORY = ROOT / "data" / "manuals"

#: One part-number-style identifier that actually occurs in this corpus (the
#: Honeywell model code) plus natural-language queries. `DX-CF14` is only in
#: the unit-test fixture, so it is both backends answering *empty* — which is
#: parity, not a divergence.
QUERIES = ["HPA5350", "filter replacement schedule", "clean the pre filter", "warranty period"]

#: How deep the cloud side is looked before a local hit is judged absent. The
#: backend ranks deliberately differ — RRF fuses two arms, the local backend
#: is strict-conjunctive — so the honest invariant is chunk presence inside
#: the retrieval window both owe a card, not rank order (RULES.md 6).
TIGER_WINDOW = 20
LOCAL_WINDOW = 5


def build_local() -> tuple[LocalRetriever, str]:
    retriever = LocalRetriever(sqlite3.connect(":memory:"))
    manuals = 0
    for path in list_pdfs(DIRECTORY):
        try:
            manual = read_manual(path, slug_from_filename(path))
        except Exception as exc:  # noqa: BLE001 - the parity run records, not raises
            print(f"  skipped {path.name}: {exc}")
            continue
        retriever.index(
            sha256_of(path),
            slug_from_filename(path),
            [(chunk.page, chunk.section, chunk.text) for chunk in chunk_manual(manual.pages)],
        )
        manuals += 1
    return retriever, f"{manuals} manuals"


def main() -> int:
    local, local_note = build_local()
    print(f"local   : FTS5 trigram, in-memory, {local_note}")

    dsn = os.environ.get("SLOTH_DATABASE_URL", "").strip()
    if not dsn:
        print("tiger   : SLOTH_DATABASE_URL not set — the cloud half is skipped, "
              "not silently compared with itself.")
        return 2
    from sloth_drawer.retrieval.tiger import TigerRetriever

    tiger = TigerRetriever.from_env()
    print(f"tiger   : pgvector + pg_textsearch, RRF k=60, {tiger._dsn_redacted}")

    diverged = 0
    partial = 0
    header = f"{'QUERY':<32} {'LOCAL TOP-5':>18} {'TIGER TOP-20 PAGES':>24}  RESULT"
    print()
    print(header)
    print("-" * len(header))
    for query in QUERIES:
        started = time.monotonic()
        local_hits = local.search(query, k=LOCAL_WINDOW)
        cloud_hits = tiger.search(query, k=TIGER_WINDOW)
        elapsed = time.monotonic() - started
        cloud_pages = {(hit.page, hit.content) for hit in cloud_hits}
        pages = ",".join(str(hit.page) for hit in cloud_hits[:LOCAL_WINDOW])

        if not local_hits:
            if not cloud_hits:
                # Both say "not in this corpus" — that *is* the same card: no card.
                print(f"{query:<32} {'(no hits)':>18} {'(no hits)':>24}  EMPTY-PARITY ({elapsed:.1f}s)")
            else:
                print(f"{query:<32} {'(no hits)':>18} {pages:>24}  DIVERGED")
                diverged += 1
            continue
        if not cloud_hits:
            print(f"{query:<32} {str([h.page for h in local_hits]):>18} {'(no hits)':>24}  DIVERGED")
            diverged += 1
            continue

        present = sum(1 for hit in local_hits if (hit.page, hit.content) in cloud_pages)
        local_pages = ",".join(str(hit.page) for hit in local_hits)
        if present == len(local_hits):
            print(f"{query:<32} {local_pages:>18} {pages:>24}  PARITY ({elapsed:.1f}s)")
        elif present:
            print(
                f"{query:<32} {local_pages:>18} {pages:>24}  "
                f"PARTIAL {present}/{len(local_hits)} ({elapsed:.1f}s)"
            )
            partial += 1
        else:
            print(
                f"{query:<32} {local_pages:>18} {pages:>24}  DIVERGED "
                f"(none of the local top-{len(local_hits)} reached the cloud top-{len(cloud_hits)})"
            )
            diverged += 1

    print()
    if diverged:
        print(f"{diverged}/{len(QUERIES)} queries diverged, {partial} partial. "
              "See RULES.md §6 — a divergence in what the backends return is a bug "
              "in one of them.")
        return 1
    print(f"0/{len(QUERIES)} diverged ({partial} partial) — every local hit is reachable "
          "from the hybrid backend's window.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
