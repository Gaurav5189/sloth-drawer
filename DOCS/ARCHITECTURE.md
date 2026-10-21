# ARCHITECTURE — Sloth Drawer

> App flow, folder & file structure, tech stack.
> Read `RULES.md` before changing anything in here — most of these decisions are load-bearing.

---

## 1. Design philosophy

**The model points. The code quotes. The code recomputes.**

The pipeline is deliberately split so that the *unreliable* component (a 1B open-weight model) is only ever
allowed to do the one thing it is good at — **locating a candidate sentence** — and every *consequential*
step is done by deterministic code:

| Step | Owner | Failure mode |
|---|---|---|
| Find candidate chunks | **code** (regex) | misses an interval → it never reaches the model |
| Decide "is there an interval here?" | **model** (270M triage) | false positive → caught by the verifier |
| Locate the sentence, name the task | **model** (1B extract) | wrong quote → caught by the verifier |
| Confirm the quote exists in the cited page | **code** | — |
| Expand the fragment to the full sentence | **code** | — |
| Compute the interval in months | **code** | — |
| Compare model vs code | **code** | → `REPAIR` |
| Compute `next_due` | **code** | — |
| Render the card | **code** | — |

Consequence: a model failure can never produce a wrong date on a card. It can only produce a *missing* card.

---

## 2. App flow

```
                      ┌──────────────────────────────────────────────┐
   data/manuals/*.pdf  │  1. INGEST      pypdf → pages[] (text + no.) │
   ──────────────────▶│                  skip image-only, record why   │
                      └───────────────────┬──────────────────────────┘
                                          ▼
                      ┌──────────────────────────────────────────────┐
                      │  2. CHUNK      page → chunks                │
                      │                 (page no + section heading)  │
                      └───────────────────┬──────────────────────────┘
                                          ▼
                      ┌──────────────────────────────────────────────┐
                      │  3. PREFILTER  regex scoring (free)          │
                      │                 score < threshold → drop     │
                      └───────────────────┬──────────────────────────┘
                                          ▼
                      ┌──────────────────────────────────────────────┐
                      │  3b. RETRIEVE  Retriever.search(q, k)        │
                      │   ├ local  : SQLite FTS5 (trigram) — default │
                      │   └ tiger  : pgvector + pg_textsearch + RRF  │
                      │                 (only if SLOTH_DATABASE_URL) │
                      └───────────────────┬──────────────────────────┘
                                          ▼
                      ┌──────────────────────────────────────────────┐
                      │  4. TRIAGE     gemma3:270m  (3s, optional)    │
                      │                 "does this state an interval?" │
                      └───────────────────┬──────────────────────────┘
                                          ▼
                      ┌──────────────────────────────────────────────┐
                      │  5. EXTRACT    gemma3:1b    (12s)             │
                      │                 ONE fact, flat JSON schema,   │
                      │                 Ollama `format` constrained  │
                      └───────────────────┬──────────────────────────┘
                                          ▼
                      ┌──────────────────────────────────────────────┐
                      │  6. VERIFY     ★ THE VERIFIER ★             │
                      │     a. find quote in cited page (verbatim)    │
                      │     b. expand to enclosing sentence          │
                      │     c. re-parse interval from that sentence  │
                      │     d. compare → PASS / REPAIR / REJECT      │
                      └───────────────────┬──────────────────────────┘
                                          ▼
                      ┌──────────────────────────────────────────────┐
                      │  7. PERSIST     sqlite3 (local state)        │
                      │     devices, tasks, evidence, verdicts,      │
                      │     service_events (last_done)               │
                      │     + optional: chunks/embeddings → Tiger    │
                      └───────────────────┬──────────────────────────┘
                                          ▼
        ┌─────────────────────────────┼─────────────────────────────┐
        ▼                             ▼                             ▼
┌───────────────┐          ┌────────────────────┐          ┌──────────────────┐
│ 8a. CARD      │          │ 8b. REPORT         │          │ 8c. NEXT DUE     │
│  HTML (A6)    │          │  report.json/.md   │          │  last_done +     │
│  + terminal   │          │  accuracy table    │          │  interval_months │
│  + web UI     │          │  + backend compare │          └──────────────────┘
└───────────────┘          └────────────────────┘
```

### 2.1 The verifier, in detail

This is the heart of the project. `extract/verify.py` is pure, deterministic, unit-testable code with
**no model calls** — it is the part worth writing 40 unit tests for.

```
verify(model_output, source_page_text) -> Verdict
```

1. **Locate.** Normalise whitespace on both the quote and the page text; find the quote's character
   offset in the page. If not found → `REJECT(reason="quote_not_in_page")`.
2. **Expand.** Walk backwards and forwards to sentence boundaries to recover the full sentence
   containing the fragment. Handle the case where the model returned several sentences.
3. **Re-parse.** Extract the interval from the *expanded sentence only*:
   `every N day|week|month|year`, `N months`, `N years`, `N days`, `N hours of (continuous) operation`,
   and the "or" / "whichever comes first" variants. → `None` means `REJECT(reason="no_interval_in_citation")`.
4. **Compare.** `model.interval_months` vs `code.interval_months`.
   Equal → `PASS`. Different → `REPAIR(model=…, code=…, sentence=…)` — **the code value wins** and the
   disagreement is recorded in the report and shown on the card as a footnote.
5. **Return.** The verdict, the verified sentence, the code interval, the page number, the section.

Edge cases that must be handled explicitly: the quote spanning a line wrap; the model returning a quote
with different Unicode quotes; the model returning the *whole* page; the page containing the same
sentence twice (take the first, and note the ambiguity).

### 2.2 Data flow invariants

- **The model never sees more than one chunk.** Prompts are built per chunk; nothing is batched.
- **The model never sees your filesystem.** It receives chunk text, nothing else.
- **Every persisted interval row carries its verdict.** There is no path that writes an interval without
  a verdict attached.
- **`next_due` is computed at read time**, never stored from a model output.

---

## 3. Folder & file structure

```
sloth-drawer/
├── INDEX.md                     # project index & doc map (created by the human)
├── PLAN.md                      # the 4-day plan, benchmark, risk register
├── PRD.md                       # requirements, users, metrics
├── ARCHITECTURE.md              # this file
├── RULES.md                     # what to use / avoid, error handling, AI boundaries
├── PHASES.md                    # phase breakdown with exit criteria
├── DESIGN.md                    # palette, type, card layout
├── MEMORY.md                    # running log — update after every task
├── README.md                    # what it is, 60-second quickstart
├── LICENSE                      # MIT
├── pyproject.toml               # deps + entry point (src layout)
├── .env.example                 # SLOTH_DATABASE_URL, SLOTH_EMBED_MODEL, SLOTH_SENTRY_DSN
├── .gitignore
│
├── src/sloth_drawer/
│   ├── __init__.py
│   ├── __main__.py               # python -m sloth_drawer
│   ├── cli.py                    # argparse: scan | card | done | report | models | index | serve
│   ├── config.py                 # paths, constants, model registry, backend selection
│   ├── errors.py                 # typed exceptions + exit codes
│   │
│   ├── corpus/
│   │   ├── __init__.py
│   │   ├── ingest.py             # pypdf → Page(text, number, source_pdf)
│   │   ├── chunk.py              # Page → Chunk(text, page, section, offsets)
│   │   └── prefilter.py          # deterministic regex scoring
│   │
│   ├── retrieval/                # ★ TWO BACKENDS, ONE INTERFACE ★
│   │   ├── __init__.py
│   │   ├── base.py               # Retriever protocol + ChunkRef dataclass
│   │   ├── local.py              # SQLite FTS5 (trigram) — the default, fully offline
│   │   └── tiger.py              # pgvector + pg_textsearch + RRF (opt-in)
│   │
│   ├── extract/
│   │   ├── __init__.py
│   │   ├── prompts.py            # prompt templates + JSON schemas (the only place they live)
│   │   ├── ollama.py             # stdlib urllib client: generate, schema, timeout, retry
│   │   ├── embed.py              # Ollama /api/embed → vectors (same local server)
│   │   ├── triage.py             # 270M yes/no gate
│   │   ├── extractor.py          # 1B one-fact-per-call
│   │   └── verify.py             # ★ THE VERIFIER ★ (pure, no model)
│   │
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── db.py                 # sqlite3 schema, migrations, connection helper
│   │   └── service_log.py        # last_done events → next_due (code only)
│   │
│   ├── vector/
│   │   ├── __init__.py
│   │   ├── schema.sql            # CREATE EXTENSION + manual_chunks + bm25 index
│   │   └── indexer.py            # chunk → embed → upsert into Tiger Cloud
│   │
│   ├── render/
│   │   ├── __init__.py
│   │   ├── theme.py              # palette + type tokens shared by HTML and text
│   │   ├── card_html.py          # A6 print card (print CSS, no web fonts)
│   │   └── card_text.py          # 80-col terminal card
│   │
│   ├── report/
│   │   ├── __init__.py
│   │   └── build.py              # accuracy table + backend comparison → report.json/.md
│   │
│   ├── web/
│   │   ├── __init__.py
│   │   ├── app.py                # FastAPI app factory
│   │   ├── routes.py             # /devices, /devices/{slug}/card, /tasks/{id}/done, /report
│   │   └── static/               # index.html, card.css  (no JS framework, no CDN)
│   │
│   └── observability/
│       ├── __init__.py
│       └── sentry.py             # optional; no-op when no DSN
│
├── bench/                        # model benchmark harness (already written, used for the post)
│   ├── final.py                  # verifier + multi-model comparison
│   ├── bench2.py                 # array-schema vs one-fact schema
│   └── validate.py               # quote expansion + repair path
│
├── tests/
│   ├── test_verify.py            # the verifier deserves the most tests
│   ├── test_prefilter.py
│   ├── test_chunk.py
│   ├── test_service_log.py
│   ├── test_cards.py
│   ├── test_report.py
│   ├── test_retrieval_local.py
│   ├── test_retrieval_parity.py  # both backends must produce the same card
│   └── test_web.py
│
├── data/
│   ├── devices.toml              # device registry (hand-edited, stdlib tomllib reads it)
│   └── manuals/                  # user's PDFs (gitignored — not ours to redistribute)
│
└── out/                          # generated: cards/, report.json, report.md (gitignored)
```

> **Pending restructure (apply at kickoff, not now).** Per `INDEX.md`, the docs move to `DOCS/`
> (`RULES.md`, `PRD.md`, `ARCHITECTURE.md`, `DESIGN.md`, `PHASES.md`, `PLAN.md`) and `MEMORY.md` moves to
> `.agents/`. `INDEX.md` stays at the project root. This has deliberately **not** been applied yet — the
> human is doing it when development starts. Nothing in the source tree depends on where these files
> live, and no import or script references a doc path.

**Dependency direction (enforced by an import-lint test):**

```
cli → corpus → retrieval → extract → verify → storage
      ↘ render ↗              ↘ report ↗   ↘ vector ↗
                                       web (imports storage + render only)
                  observability (side-channel only, imported by nobody below it)
```

`verify.py` and `prefilter.py` import **nothing** from the project except `errors.py`. They are pure
functions over text. This is what makes them testable without a model, and it is what makes the
verifier trustworthy enough to be the headline of the post.

`retrieval/` depends on `corpus/` (for the `ChunkRef` shape) and on nothing else. `vector/` depends on
`retrieval/base.py` and `extract/embed.py` only — **it must not import `storage/`**, which is what
enforces the "no identifiers in the cloud" boundary in `RULES.md` §3.1a. `web/` may read `storage/` and
`render/`, and nothing else.

---

## 4. Tech stack

### 4.1 Language & runtime
| | |
|---|---|
| Language | Python 3.11+ (reference box: 3.14.8) |
| Package manager | `uv` (present on the box) with a `pyproject.toml` that also works with `pip` |
| Layout | `src/` layout, console script `sloth-drawer` |
| Target platform | Linux/macOS/Windows. No platform-specific calls in the core path |

### 4.2 Runtime dependencies (core path)
| Package | Version | Why | Rejected alternative |
|---|---|---|---|
| `pypdf` | ≥4 | PDF text + per-page extraction, pure Python | `pdfplumber` (heavier, slower); `PyMuPDF` (C wheel, licence noise) |
| `fastapi` | ≥0.115 | the web surface: device list, card preview, mark-done | `django`, `flask`, `gradio`, `streamlit` |
| `uvicorn` | ≥0.30 | ASGI server for the web surface | `gunicorn` (not needed for a single-process app) |
| `psycopg[binary]` | ≥3.2 | Postgres v3 driver for the Tiger Cloud backend | `psycopg2` (older); `asyncpg` (async-only) |
| `pgvector` | ≥0.3 | `pgvector.psycopg.register_vector` adapter for the `vector(N)` column | raw string casts |
| *(stdlib)* `urllib.request` | — | Ollama HTTP. Zero deps, full control over timeout/retry | `ollama` SDK (adds a dep for one POST) |
| *(stdlib)* `sqlite3` | — | state + service log + **FTS5 local search** (verified on the reference box: SQLite 3.54.0, FTS5 with the `trigram` tokenizer) | SQLAlchemy, ORM, `whoosh`, `rank_bm25` |
| *(stdlib)* `tomllib` | — | reads `data/devices.toml` | PyYAML (a dep for one file) |
| *(stdlib)* `json`, `re`, `dataclasses`, `pathlib`, `argparse`, `logging` | — | — | — |

**Core install is six dependencies and still installs in under a minute** — all six ship wheels. That is
a feature, and it goes in the post.

### 4.3 Remaining optional extras
| Extra | Packages | Purpose | Why still optional |
|---|---|---|---|
| `observability` | `sentry-sdk` | agent tracing | Needs a Sentry account and a DSN |
| `forecast` | `tabpfn` | TabPFN spend forecast | Needs a Prior Labs non-commercial licence |

`web` and `vector` are **not** extras — they are core, because the web surface and the vector index are
part of the product rather than decoration.

### 4.4 Model layer
| Role | Model | Size | Measured on the reference box |
|---|---|---|---|
| Triage (optional) | `gemma3:270m` | 291 MB | 3.0–6.8 s, 9–16 tok/s |
| **Extractor (default)** | `gemma3:1b` | 806 MB | 12–13 s, 4.7–13.4 tok/s, passes both schema patterns |
| Extractor (alternative) | `phi4-mini:latest` | 2.5 GB | 27–48 s, 1.4–3.5 tok/s, fails the array-schema pattern |
| **Embedder** | `nomic-embed-text` | 274 MB | 768 dims, 2K context — the default for the `vector` backend |
| (future) Vision | `gemma3:4b` | 3.4 GB | not needed in v1 — no image path |

**The embedder runs on the same local Ollama as the generator.** No embedding API, no cloud inference,
no `torch`/`sentence-transformers`. `SLOTH_EMBED_DIMS` must equal the `vector(N)` width in the schema;
a mismatch is a startup error, not a runtime surprise.

Served by a **local** Ollama. `config.py` refuses to start if `OLLAMA_HOST` resolves to a non-loopback
address (see `RULES.md` §AI boundaries).

### 4.4b Retrieval backends — one interface, two implementations

`retrieval/` exposes exactly one public interface:

```python
class Retriever(Protocol):
    def search(self, query: str, k: int) -> list[ChunkRef]: ...
```

`ChunkRef` carries `(manual_sha, page, section, content, score, backend)`. The backend is selected in
`config.py` and injected; **there is no `if backend ==` anywhere in the pipeline.**

| | `local` | `tiger` |
|---|---|---|
| Engine | SQLite FTS5, `tokenize='trigram'` | pgvector (HNSW-free at this size) + `pg_textsearch` BM25 |
| Fusion | n/a (single retriever) | Reciprocal Rank Fusion, `k = 60`, ranks not scores |
| Needs a network | **No** | Yes |
| Needs configuration | None | `SLOTH_DATABASE_URL` |
| Embeddings | No | Yes (`nomic-embed-text`, 768 dims) |
| Good at | part numbers, identifiers, exact phrases | paraphrases, rare words, cross-language |

The local backend uses the **trigram** tokenizer deliberately: it matches part numbers such as
`DX-CF14` that a word tokenizer splits and that embeddings flatten into the surrounding prose. That is
precisely the blind spot BM25 covers, which is why the local backend is a genuine peer rather than a
degraded fallback.

**The Tiger Cloud schema** is in `vector/schema.sql` (idempotent, applied by `sloth-drawer index`):

```sql
CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE;   -- brings in pgvector
CREATE EXTENSION IF NOT EXISTS pg_textsearch;          -- BM25 full-text, PG 17/18

CREATE TABLE IF NOT EXISTS manual_chunks (
  id          BIGSERIAL PRIMARY KEY,
  device_slug TEXT NOT NULL,
  manual_sha  TEXT NOT NULL,
  page        INTEGER NOT NULL,
  section     TEXT,
  content     TEXT NOT NULL,
  embedding   vector(768),
  indexed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (manual_sha, page, content)
);

CREATE INDEX IF NOT EXISTS manual_chunks_bm25_idx
  ON manual_chunks USING bm25(content)
  WITH (text_config='english');
```

**HNSW is deliberately omitted at this corpus size.** With a few thousand chunks the planner will pick a
sequential scan anyway and the BM25 index does the work. Add
`CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)` only past ~10k chunks, and record the
decision in `MEMORY.md`.

**Hybrid query** — BM25 (keyword) and vector (semantic) in parallel, fused with RRF:

```sql
WITH vec AS (
  SELECT id, ROW_NUMBER() OVER (ORDER BY embedding <=> %s::vector) AS rank
  FROM manual_chunks ORDER BY embedding <=> %s::vector LIMIT 20
), kw AS (
  SELECT id, ROW_NUMBER() OVER (ORDER BY content <@> to_bm25query(%s,'manual_chunks_bm25_idx')) AS rank
  FROM manual_chunks
  ORDER BY content <@> to_bm25query(%s,'manual_chunks_bm25_idx') LIMIT 20
)
SELECT m.id, m.device_slug, m.page, m.section,
       COALESCE(1.0/(60+v.rank),0) + COALESCE(1.0/(60+k.rank),0) AS score
FROM manual_chunks m
LEFT JOIN vec v ON v.id = m.id
LEFT JOIN kw  k ON k.id = m.id
WHERE v.id IS NOT NULL OR k.id IS NOT NULL
ORDER BY score DESC LIMIT %s;
```

Three things that are easy to get wrong and are therefore rules (see `RULES.md` §1.3):
always use `to_bm25query(text, 'index_name')` rather than the bare form; BM25 scores are **negative and
lower is better**, so never normalise them against a cosine similarity; and RRF fuses **ranks**, not
scores — that is the entire point of choosing it.

### 4.5 Sentry
`sentry-sdk` with `traces_sample_rate=1.0`. One transaction per manual, one span per pipeline stage
(`ingest`, `chunk`, `prefilter`, `triage`, `extract`, `verify`), with `gen_ai.usage.input_tokens` and
`gen_ai.usage.output_tokens` on the model spans. No-op when `SLOTH_SENTRY_DSN` is unset — the import is
lazy so the package stays optional.

### 4.6 Deployment
- **Render** (for the "Best Use of Render" category): the FastAPI app as a web service. Note that the
  free tier sleeps — the demo should tolerate a cold start, or serve a pre-generated card set.
- **`.tech` domain** (for the "Best Use of a .tech Domain" category): free first year via
  `hacktoberfest.com/my/promos`, pointed at the Render deployment.
- **Tiger Cloud** (for the "Best Use of Tiger Data" category): the Postgres service holding the
  `manual_chunks` table. The service URL comes from the console's *Download the config* file or from
  `tiger db uri`; it is read from `SLOTH_DATABASE_URL` and never committed. The Tiger CLI is a
  **developer convenience for provisioning only** — the application never shells out to it.

### 4.7 Explicitly not used
`torch`, `transformers`, `langchain`, `llama-index`, `crewai`, `autogen`, `openai`, `anthropic`,
`google-genai`, `chromadb`, `langgraph`, `pydantic-ai`, `gradio`, `streamlit`, `docker` (not needed),
`pre-commit` (nice-to-have, added in Phase 5 if time allows). Reasons in `RULES.md` §What to avoid.

---

## 5. State model

```sql
CREATE TABLE devices (
  id            INTEGER PRIMARY KEY,
  slug          TEXT UNIQUE NOT NULL,      -- slugified device name
  name          TEXT NOT NULL,
  manufacturer  TEXT,
  model         TEXT,
  category      TEXT,
  manual_path   TEXT,                      -- relative to data/manuals
  created_at    TEXT NOT NULL
);

CREATE TABLE intervals (
  id            INTEGER PRIMARY KEY,
  device_id     INTEGER NOT NULL REFERENCES devices(id),
  task          TEXT NOT NULL,             -- "Pre-Carbon filter replacement"
  section       TEXT,                      -- "4.2 Filter Maintenance"
  page          INTEGER,                   -- 1-indexed
  interval_months REAL,                    -- COMPUTED BY CODE, never by the model
  model_interval_months REAL,              -- what the model claimed, for the report
  evidence      TEXT,                      -- the verified source sentence
  model_quote   TEXT,                      -- what the model pointed at
  verdict       TEXT NOT NULL,             -- PASS | REPAIR | REJECT
  reject_reason TEXT,
  model_id      TEXT NOT NULL,             -- "gemma3:1b"
  prompt_hash   TEXT,                      -- reproducibility
  created_at    TEXT NOT NULL,
  UNIQUE(device_id, task, page)
);

CREATE TABLE service_events (
  id            INTEGER PRIMARY KEY,
  interval_id   INTEGER NOT NULL REFERENCES intervals(id),
  done_at       TEXT NOT NULL,             -- ISO date
  note          TEXT
);

CREATE TABLE runs (
  id            INTEGER PRIMARY KEY,
  started_at    TEXT NOT NULL,
  finished_at   TEXT,
  model_id      TEXT,
  manuals       INTEGER, chunks INTEGER, candidates INTEGER,
  found INTEGER, passed INTEGER, repaired INTEGER, rejected INTEGER,
  seconds REAL, tokens INTEGER, cost_usd REAL DEFAULT 0
);
```

`next_due` is **not** a column. It is `MAX(done_at) + interval_months` computed at read time by
`storage/service_log.py`, so that changing an interval retroactively changes the schedule — the same
reason the PRD prefers a "last done" log over a mutable "next due" field.

---

## 6. Extension points (deliberately left open)

- **A second verifier mode** — `verify.py` exposes `verify()`; a `verify_time_interval()` can be added
  for "within 90 days of purchase" style wording without touching the caller.
- **A different task ontology** — `prompts.py` is the only place schemas live; adding a "cleaning" or
  "inspection" task class means adding a schema there and nothing else.
- **A new card layout** — `render/theme.py` holds the tokens; `card_html.py` and `card_text.py` consume
  them. A second layout (index card, A4 sheet) is a new renderer over the same tokens.
- **A second corpus source** — `corpus/ingest.py` reads PDFs; a future `.epub` or HTML manual source
  needs a new ingester emitting the same `Page` objects.
