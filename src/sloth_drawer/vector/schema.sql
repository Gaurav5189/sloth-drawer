-- Sloth Drawer's cloud schema, applied idempotently by vector/indexer.py.
-- RULES.md 1.3 is the source of truth for this file; the notes there were
-- measured against the live service (Tiger Cloud, PostgreSQL 18.6, 2026-10-22).

CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE;   -- brings in pgvector
CREATE EXTENSION IF NOT EXISTS pg_textsearch;          -- BM25 full-text, PG 17/18

-- The app owns its own schema, so nothing lands in `public` and the DDL is
-- scoped to one namespace (PLAN.md risk register: never point DDL at prod).
CREATE SCHEMA IF NOT EXISTS sloth;
SET search_path TO sloth, public;

-- The cloud boundary is a schema constraint, not a promise (RULES.md 3.1a):
-- every column here is manual chunk text or an embedding. There is no column
-- that could hold a device name, a serial number, a purchase date or anything
-- else identifying the user's home — and the writer (vector/indexer.py) never
-- receives one.
CREATE TABLE IF NOT EXISTS manual_chunks (
  id          BIGSERIAL PRIMARY KEY,
  device_slug TEXT NOT NULL,
  manual_sha  TEXT NOT NULL,          -- sha256 of the source PDF
  page        INTEGER NOT NULL,
  section     TEXT,
  content     TEXT NOT NULL,
  embedding   vector(768),             -- nomic-embed-text
  indexed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (manual_sha, page, content)
);

-- `text_config` is required by the bm25 access method; omitting it fails with
-- "text_config parameter is required for bm25 indexes" (RULES.md 1.3).
-- CREATE INDEX takes an UNQUALIFIED index name: PostgreSQL's grammar has no
-- qualified index name, and `CREATE INDEX sloth.name` is a syntax error.
CREATE INDEX IF NOT EXISTS manual_chunks_bm25_idx
  ON manual_chunks USING bm25(content)
  WITH (text_config='english');

-- HNSW is deliberately omitted at this corpus size (a few thousand chunks:
-- the planner will choose a sequential scan anyway, and the BM25 index does
-- the work). Add `CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)`
-- only past ~10k chunks, then record it in MEMORY.md -> Decisions.
