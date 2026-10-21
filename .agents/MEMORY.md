# MEMORY — Sloth Drawer

> Update this file after every completed task and whenever the working file changes. Newest entries on top. Keep it short and factual.

## Current Status
- **Phase:** 0 — Setup (not started)
- **Working on:** —
- **Files/modules in progress:** —
- **Blocked / waiting for answer:** Tiger Cloud CLI token is expired — `tiger auth login` required before
  the service URL can be fetched (Phase 0 task)

## Completed
- [x] Planning: PRD, ARCHITECTURE, RULES, PHASES, DESIGN written
- [x] PLAN.md written (4-day schedule, benchmark data, risk register, post outline)
- [x] Model benchmark run on the reference box — results in PLAN.md §3.1, harness in `bench/`
- [x] Design decisions locked: A6 card, system font stacks only, verdict glyphs carry state without colour

## Decisions Log
| Date | Decision | Reason |
|---|---|---|
| 2026-10-22 | Project = "Sloth Drawer": manual PDFs → one maintenance card per device | Only topic with 0/206 Week-3 competition and a concrete privacy stake |
| 2026-10-22 | Build #1 over #2 (Sloth Drawer) | #1's extraction surface is 3 scalars; #2 needs 3 date fields + cross-doc corroboration |
| 2026-10-22 | Scope cut: "last done" instead of "bought on" | Removes a whole input field, the recurrence parsing, and the "720 hours" edge case |
| 2026-10-22 | Default extractor = `gemma3:1b` (806 MB), not `phi4-mini` (2.5 GB) | Measured 2.2–3.8× faster on 4 CPU cores, 1/3 the RAM, and it does not swap |
| 2026-10-22 | `phi4-mini` kept as a documented `--model` alternative | It is the best "swap models / change how your agent behaves" data point for the post |
| 2026-10-22 | `gemma3:270m` used as triage, not extraction | 16 tok/s but it got the interval wrong; the verifier caught it — that failure is post material |
| 2026-10-22 | One fact per call, flat JSON schema, never an array | Measured: `phi4-mini` returns `{"intervals": []}` under an array schema; flat schema passes on all models |
| 2026-10-22 | "The model points, the code quotes, the code recomputes" is the core design | Only structure that makes a wrong model output incapable of producing a wrong date |
| 2026-10-22 | Core install is one dependency (`pypdf`); stdlib for HTTP, sqlite3, tomllib, argparse | A local-first tool should not drag in a framework |
| 2026-10-22 | System font stacks only, no web fonts | A tool that downloads a typeface from Google contradicts its own premise |
| 2026-10-22 | A6 (105×148mm) card, one device per card, hero = soonest due | A physical artifact taped to a device; recency is what a sloth can act on |
| 2026-10-22 | Target partner categories: Gemma, Render, Sentry, Entire, .tech (+ Tiger Data / TabPFN as stretch) | Each has 0–1 Week-3 entries; Gemma is the only one with a field (13) |
| 2026-10-22 | Cut order if behind: web UI → vector index → TabPFN forecast | Card + report + post are the deliverable; the rest is a category bonus |
| 2026-10-22 | `web` (fastapi, uvicorn) and `vector` (psycopg[binary], pgvector) moved from optional extras to **core** dependencies | Both are part of the product, not decoration. Only `observability` and `forecast` stay optional — each needs an external account or licence |
| 2026-10-22 | **Dual retrieval backend** behind one `Retriever` interface: `local` (SQLite FTS5, trigram) and `tiger` (pgvector + `pg_textsearch` BM25 + RRF) | A cloud DB would break the offline thesis. Making the cloud an *enhancement* keeps the "works on a plane" claim true while still earning the Tiger Data category honestly |
| 2026-10-22 | Tiger Cloud = **pgvector + `pg_textsearch` BM25, fused with RRF (k=60)** | Vector-only search flattens identifiers like `DX-CF14`; BM25 catches them. RRF fuses ranks, so no score normalisation is needed |
| 2026-10-22 | Local backend uses SQLite FTS5 with the **`trigram` tokenizer** | Verified on the reference box (SQLite 3.54.0, FTS5 + trigram present). It matches part numbers a word tokenizer splits — so the local backend is a peer, not a downgrade |
| 2026-10-22 | Embeddings via **Ollama `nomic-embed-text`** (274 MB, 768 dims), not `sentence-transformers` | Same local Ollama as the generator. No torch, no cloud embedding API |
| 2026-10-22 | **Cloud data boundary is a schema constraint**: `manual_chunks` holds chunk text + embedding only — no device names, serial numbers, purchase dates or service history | The "why open" claim is only worth anything if it is enforced. A `device_name` column would be a design bug, not a feature |
| 2026-10-22 | App DSN comes from `SLOTH_DATABASE_URL`; the Tiger CLI is used for **provisioning only**, never at runtime | The app must not shell out to the CLI, and must not break when the CLI is absent |
| 2026-10-22 | The Tiger CLI config points at a **`read_only: prod`** service (`db-75294`) | The app needs DDL (`CREATE EXTENSION`, `CREATE TABLE`). Use a separate dev service or schema. Never point migrations at prod |
| 2026-10-22 | Docs will move to `DOCS/` and `MEMORY.md` to `.agents/` per `INDEX.md` — **at kickoff, not now** | The human is making that change. Nothing in the source tree depends on doc paths, so there is no conflict either way |

## Open Questions
- Confirm the device class for the corpus (air purifiers vs robot vacuums vs coffee machines) — decided Fri morning at the corpus checkpoint.
- Is `pytest` available on the box, or should the tests use stdlib `unittest`? — decide in Phase 0 and record here.
- Does the reference corpus support a two-device-class demo? — only if time allows after the report.
- Which Tiger Cloud service/schema should the app point at — a new dev service, or a schema inside `db-75294`? — the app needs DDL, so it cannot be the `read_only: prod` default. Decide in Phase 0.
- Does the shared Tiger service already have `vector` and `pg_textsearch`, or must they be enabled (which may need a maintenance window)? — check in Phase 0.

## Known Issues / Tech Debt
- The 291 MB triage model (`gemma3:270m`) **fails** the extraction task (claimed 1 month, cited a sentence with no interval). It is only ever used for the yes/no gate. Do not promote it to extractor without re-running `bench/`.
- `phi4-mini` under an array schema returns a schema-valid but semantically empty result. The extractor therefore never uses an array schema.
- Ollama may re-sort JSON schema keys alphabetically on the native chat path. Assert on schema keys in tests; do not trust the round-trip.
- `bench/` numbers were taken on a 4-core / 7.5 GB / no-GPU box with ~2.9 GB free RAM. Re-run on the final machine and update PLAN.md §3.1 if they move.
- **The Tiger CLI token is expired.** `tiger db uri` / `tiger db ping` / `tiger service list` all fail with `oauth2: token expired and refresh token is not set`. Fix: `tiger auth login`.
- `~/.config/tiger/config.yaml` has `read_only: prod` and `service_id: db-75294`. The app needs DDL, so it must not use that service as-is.
- `pg_textsearch` needs PostgreSQL 17/18 and may only become available after a maintenance window on an existing Tiger service. Fallback: plain `ts_rank_cd` over a `tsvector` column, or the local backend.
- BM25 scores in both `pg_textsearch` and SQLite's `bm25()` are **negative and lower is better**. Do not normalise them against a cosine similarity, and do not compare across backends — RRF fuses ranks, not scores.

## Next Up
1. Phase 0 tasks from `PHASES.md` — repo init, `pyproject.toml` (core deps `pypdf` / `fastapi` / `uvicorn` /
   `psycopg[binary]` / `pgvector`), `.env.example`, `config.py`, `errors.py`, `models.py`, test scaffold.
2. `tiger auth login` → `tiger db uri` → check which extensions the service already has. Do **not** use the
   `read_only: prod` service for DDL.
3. **Fri 09:00 hard checkpoint** — collect 10–12 text-based manual PDFs in one device class. If fewer than 8 usable by Fri 18:00, switch device class.

## Update Template
```
### YYYY-MM-DD
- Done: <what>
- Files: <paths>
- Next: <what>
- Notes/Blockers: <if any>
```

---

### 2026-10-22
- Done: Researched Week 3 competition (206 submissions, saturation map, partner-category counts); benchmarked `gemma3:270m` / `gemma3:1b` / `phi4-mini` on the reference box; designed the verifier and validated it against four failure modes; wrote all planning documents.
- Files: `PLAN.md`, `PRD.md`, `ARCHITECTURE.md`, `RULES.md`, `PHASES.md`, `DESIGN.md`, `MEMORY.md`, `bench/final.py`, `bench/bench2.py`, `bench/validate.py`
- Next: Phase 0 — scaffold the project and start the corpus collection.
- Notes/Blockers: None. Note that `phi4-mini` is already pulled locally; `gemma3:1b` and `gemma3:270m` were pulled during the benchmark.
