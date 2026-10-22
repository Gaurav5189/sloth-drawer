# MEMORY — Sloth Drawer

> Update this file after every completed task and whenever the working file changes. Newest entries on top. Keep it short and factual.

## Current Status
- **Phase:** 1 — Corpus & extraction engine → **complete**; Phase 2 (cards, state, report) is next
- **Working on:** —
- **Files/modules in progress:** none — Phase 1 landed and is committed
- **Blocked / waiting for answer:** none

## Completed
- [x] Planning: PRD, ARCHITECTURE, RULES, PHASES, DESIGN written
- [x] PLAN.md written (4-day schedule, benchmark data, risk register, post outline)
- [x] Model benchmark run on the reference box — results in PLAN.md §3.1, harness in `bench/`
- [x] Design decisions locked: A6 card, system font stacks only, verdict glyphs carry state without colour
- [x] **Phase 0** — repo scaffold: `pyproject.toml` (src layout), `README.md`, `LICENSE` (MIT),
      `.gitignore`, `.env.example`, `src/sloth_drawer/{__init__,__main__,cli,config,errors,models}.py`
- [x] **Phase 0** — `config.py` (paths, env overrides, loopback guard, backend selection, DSN redaction),
      `errors.py` (full `RULES.md` §2.2 hierarchy + exit codes), `models.py` (registry + `check_ollama`
      / `check_model_pulled` / `require_model`)
- [x] **Phase 0** — `sloth-drawer models` works: exits 0 with the registry table when Ollama is up,
      exits 2 with `Cannot reach Ollama at … Start it with "ollama serve".` when it is down
- [x] **Phase 0** — tests: 52 passing, including the AST-based import-direction test that enforces
      `RULES.md` §3.1a (the `vector/` package cannot import `storage/`) and the purity of `verify.py`
- [x] **Phase 0** — `bench/README.md` written (how to re-run every published number)
- [x] **Phase 0** — Tiger Cloud: `tiger auth login` refreshed, service URL fetched, extensions installed
- [x] `ruff check .` / `ruff format --check .` clean, `mypy` clean, `pytest` green
- [x] **Phase 1** — **corpus collected: 19 text-based air-purifier manuals** across 7 brands
      (Coway, Levoit, Honeywell, Blueair, Medify, Winix, +1 skipped Airthereal). 31 candidates fetched,
      12 skipped and recorded with reasons (`data/corpus_sources.md`): 4 image-only scans, 6 hosts
      returned HTTP 403, 1 unreadable by pypdf, 1 single-page pypdf failure recovered per-page
- [x] **Phase 1** — `corpus/ingest.py` (pypdf → `Page`, per-page error tolerance so one broken page
      does not lose a manual, `sha256` per manual for the vector index)
- [x] **Phase 1** — `corpus/chunk.py` (verbatim page slices with page no + section heading; a new
      heading starts a new chunk so a citation's section always matches its text)
- [x] **Phase 1** — `corpus/prefilter.py` (pure regex scoring + **candidate sentences**: the code
      enumerates the interval-bearing sentences so every interval gets exactly one model call)
- [x] **Phase 1** — `extract/ollama.py` (stdlib client, fixed request shape, timeout/backoff/retry,
      token accounting), `extract/prompts.py` (both prompts + JSON schemas, `PROMPT_VERSION`),
      `extract/triage.py`, `extract/extractor.py` (one fact per call, one repair attempt)
- [x] **Phase 1** — `extract/verify.py` — **THE VERIFIER**: locate → expand → re-parse → compare,
      with the four rejection reasons and line-aware sentence expansion
- [x] **Phase 1** — `retrieval/base.py` + `retrieval/local.py` (SQLite FTS5, trigram, `bm25()`)
- [x] **Phase 1** — `pipeline.py` + `sloth-drawer scan` — full corpus run, results in `out/scan-phase1.txt`


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
| 2026-10-22 | Test runner = **`pytest`**, as a `dependency-groups.dev` entry (not a runtime dependency) | `RULES.md` §1.1 says "stdlib `unittest` (or `pytest` if already installed — decide in Phase 0 and record it)". `pytest` was not installed, but `RULES.md` §5 and every phase's exit criteria say "`pytest` green", so the doc set already assumes it. The dev group keeps the shipped install to the six core dependencies |
| 2026-10-22 | `bench/` is **excluded from `ruff`**, `src/` and `tests/` are linted in full | `bench/` is the measurement harness whose exact source produced the numbers published in the post. Reformatting it would change the artefact a reviewer is asked to trust. `pyproject.toml` carries the reason inline |
| 2026-10-22 | `PROMPT_VERSION` lives in `config.py`; `extract/prompts.py` re-exports it | `PHASES.md` Phase 0 puts the constant in `config.py`, `RULES.md` §3.4 says "`prompts.py` exposes a `PROMPT_VERSION`". Re-exporting satisfies both without a second source of truth, and keeps the dependency direction intact (`extract` → `config` is a downward edge) |
| 2026-10-22 | Tiger Cloud service **`db-75294` / `vhr6dh202x` is `Environment: DEV`**, so the app's DDL is safe on it | The `read_only: prod` config only forces read-only for services *tagged* PROD. This one is DEV, so `read_only=prod` leaves it writable — the "never point DDL at a prod service" rule is satisfied without provisioning a second service |
| 2026-10-22 | The Tiger service's **master password was reset** (`tiger service update-password`) | The password in the OS keyring no longer authenticated (`FATAL: password authentication failed for user "tsdbadmin"`), so the service was unusable from the CLI and from the app. A fresh random password was generated, stored in the keyring, and the DSN written to the gitignored `.env` |
| 2026-10-22 | The app's Postgres objects live in a dedicated **`sloth` schema**, not `public` | Keeps `manual_chunks` off the default search path and makes the "the cloud holds only chunk text" boundary visible in the schema itself. It also forces the BM25 index name to be schema-qualified, which is the correct form anyway |
| 2026-10-22 | `RULES.md` §1.3 and `ARCHITECTURE.md` §4.4b **corrected**: the BM25 index name in `to_bm25query` must be schema-qualified; `CREATE INDEX` takes an unqualified index name; the one-argument `to_bm25query(text)` overload is a trap | The original text was wrong on two of these and would have cost an afternoon in Phase 4. All four rules were measured against the live service (PG 18.6, pg_textsearch 1.5.1), not read from documentation |
| 2026-10-22 | **Corpus device class = air purifiers** | The bench harness, `DESIGN.md`'s A6 mockup and `PLAN.md`'s post outline already speak about air purifiers; switching class would contradict all three. Supply of text-based PDFs is also excellent (19 usable from 31 candidates) |
| 2026-10-22 | **`candidate_sentences`**: the code enumerates interval-bearing sentences and builds one short excerpt per sentence; the model is called once per excerpt | "One fact per call" alone finds only one interval per chunk. Making the *code* choose the candidates keeps C5 (one excerpt per call) and RULES §4.3 (the model never chooses the next chunk) while finding every interval. The model still points; the code still recomputes |
| 2026-10-22 | **The excerpt keeps one neighbouring sentence on each side** | Context is what lets the model name the task ("Pre-Carbon filter replacement" not "filter"), and it keeps the quote inside a readable stretch. A narrower window found fewer, vaguer task labels |
| 2026-10-22 | **Interval unit conversions are stated in the prompt AND implemented in the code, from one table** (30 days = 1 month, 4 weeks = 1 month, 12 months = 1 year, 720 hours = 1 month; ranges take the midpoint) | If the model's rule and the code's rule differ, every "every 90 days" becomes a false REPAIR. `prompts.CONVERSION_RULE` and `verify.MONTHS_PER_UNIT` must stay in step — pinned by tests |
| 2026-10-22 | **`Interval` carries `value`/`unit` as the manual states them, plus `months` for scheduling** | The card shows the manufacturer's own number in the manufacturer's own unit ("2 weeks", not "0.5 months"); the schedule is computed from months. Ranges keep their range form ("3-6 months") |
| 2026-10-22 | **Sentence expansion is line-aware**: `_TERMINATOR` skips abbreviations ("Part No."), a short non-terminating line acts as a boundary (headings, table rows), and over-long "sentences" fall back to a ±200-char window | A naive "."-based split cut "The Pre-Carbon filter (Part No." off its own sentence and ran back through headings to the manual's title. All three behaviours are pinned by tests |
| 2026-10-22 | **`prefilter._flatten` and `verify.normalise` must stay identical** (dashes, curly quotes, digit commas, dash-spaces, "six(6)") | A real manual writes "2–4 weeks", "1 - 2 months" and "six(6) months"; the model returns "1-2 months". If the two flattenings drift, a found interval cannot be verified or a real quote is rejected. `verify.py` cannot import `prefilter` (purity), so a test pins them together |
| 2026-10-22 | **Triage is opt-in (`--triage`), not the default** | The pre-filter already removes ~95% of chunks, so the gate saves almost nothing on this corpus, and a weak 270M "no" loses intervals the extractor would have verified. A triage *failure* now falls through to extraction rather than losing the candidate |
| 2026-10-22 | **Per-page extraction tolerance in `ingest`**: a page that fails is recorded, the manual keeps its other pages | `medify-ma-25` and `winix-a230` each have a page pypdf cannot parse; whole-file skipping would have lost two manuals that are 90% readable |
| 2026-10-22 | **`pipeline.py` added** (not in the original ARCHITECTURE file tree) | The scan orchestration — ingest → chunk → prefilter → triage → extract → verify, with the failure policy at each stage — needs a home that is neither the CLI nor any one stage. Noted for the ARCHITECTURE file tree |

## Measured on the reference box (2026-10-23)
| Thing | Value | How it was measured |
|---|---|---|
| SQLite | **3.54.0**, FTS5 enabled, **`trigram` tokenizer works** | `sqlite3 :memory: "CREATE VIRTUAL TABLE t USING fts5(c, tokenize='trigram')"` + a `DX-CF14` match |
| Cold core install | **`uv sync --no-group dev` = 3.66 s** (empty cache, no venv, 19 packages) | `time UV_CACHE_DIR=<empty> uv sync --no-group dev` — the `RULES.md` §1.1 budget is 60 s |
| Python | 3.14.8 (uv created the venv with 3.14.7) | `python3 --version` |
| Ollama | 0.40.7, CPU only, 4 cores / 7.5 GB | `ollama serve` log |
| Postgres (Tiger Cloud) | **18.6**, `pg_textsearch` 1.5.1, `vectorscale` 0.9.0, `vector` 0.8.7 | `tiger db query "SELECT version()"` + `pg_extension` |
| Corpus scan (19 manuals) | **771 s (12:51)**, 63 candidates, 22401 tokens, **22 PASS / 13 REPAIR / 7 REJECT / 21 SKIP** | `uv run sloth-drawer scan data/manuals` — wall-clock with Ollama running |

## Open Questions
- Phase 2 scope: the card layout and the `done` command are designed; the web UI is the stretch target.

## Known Issues / Tech Debt
- The 291 MB triage model (`gemma3:270m`) **fails** the extraction task (claimed 1 month, cited a sentence with no interval). It is only ever used for the yes/no gate. Do not promote it to extractor without re-running `bench/`.
- `phi4-mini` under an array schema returns a schema-valid but semantically empty result. The extractor therefore never uses an array schema.
- Ollama may re-sort JSON schema keys alphabetically on the native chat path. Assert on schema keys in tests; do not trust the round-trip.
- `bench/` numbers were taken on a 4-core / 7.5 GB / no-GPU box with ~2.9 GB free RAM. Re-run on the final machine and update PLAN.md §3.1 if they move. **Note: this box now has ~1.9 GB free with Ollama running, so the re-run may be slower.**
- BM25 scores in both `pg_textsearch` and SQLite's `bm25()` are **negative and lower is better**. Do not normalise them against a cosine similarity, and do not compare across backends — RRF fuses ranks, not scores.
- `to_bm25query(text)` (one argument) resolves only for a *typed* argument — a bare literal fails with `function to_bm25query(unknown) does not exist`. Always use the two-argument form with a schema-qualified index name.
- `requirements.txt` is generated by `uv pip compile pyproject.toml -o requirements.txt` — **not** by a human. `pyproject.toml` stays the source of truth; the file is a pip-compatible export (`RULES.md` §1.1 bans requirements.txt *as the source of truth*, not as an export).
- `~/.config/tiger/config.yaml` had `service_id: db-75294` (a **name**); the CLI requires an **ID**. Changed to `vhr6dh202x`. The `read_only: prod` key was left alone — it only affects PROD-tagged services, and this one is DEV.

## Next Up
1. **Phase 2** — `storage/db.py` + `storage/service_log.py`, `data/devices.toml` is already written,
   `render/{theme,card_html,card_text}.py`, `report/build.py`, the `card`/`done`/`report` subcommands.
2. `tiger db uri --with-password` is the way to refresh the DSN if the password changes again; the
   current one lives in the gitignored `.env`.
3. Phase 4 wires the retriever into the scan and runs the backend parity test — deferred until both
   backends exist, so parity can actually be measured rather than asserted.


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
- Done: Phase 0 — Setup & harness. Repo scaffolded (`pyproject.toml`, `README.md`, `LICENSE`, `.gitignore`,
  `.env.example`); `config.py`, `errors.py`, `models.py`, `cli.py` written; 52 tests green including the
  AST import-direction test; `bench/README.md` written; Tiger Cloud auth refreshed and the DEV service
  prepared (`pg_textsearch` + `vectorscale` installed, `sloth` schema reserved, DSN in the gitignored `.env`).
- Files: `pyproject.toml`, `uv.lock`, `README.md`, `LICENSE`, `.gitignore`, `.env.example`,
  `src/sloth_drawer/{__init__,__main__,cli,config,errors,models}.py`,
  `tests/{test_errors,test_config,test_models,test_import_direction}.py`, `bench/README.md`,
  `DOCS/RULES.md` (§1.3 corrected), `DOCS/ARCHITECTURE.md` (§4.4b corrected), `.agents/MEMORY.md`
- Next: Phase 1 — collect the corpus and build `corpus/` → `extract/` → `retrieval/local.py`.
- Notes/Blockers: none. Two things to remember — the models were **not** pulled on this box, so
  `gemma3:270m`, `gemma3:1b`, `nomic-embed-text` and `phi4-mini` were pulled during Phase 0; and the
  Tiger service password was reset because the keyring copy no longer authenticated.

### 2026-10-22
- Done: Researched Week 3 competition (206 submissions, saturation map, partner-category counts); benchmarked `gemma3:270m` / `gemma3:1b` / `phi4-mini` on the reference box; designed the verifier and validated it against four failure modes; wrote all planning documents.
- Files: `PLAN.md`, `PRD.md`, `ARCHITECTURE.md`, `RULES.md`, `PHASES.md`, `DESIGN.md`, `MEMORY.md`, `bench/final.py`, `bench/bench2.py`, `bench/validate.py`
- Next: Phase 0 — scaffold the project and start the corpus collection.
- Notes/Blockers: None. Note that `phi4-mini` is already pulled locally; `gemma3:1b` and `gemma3:270m` were pulled during the benchmark. **[Corrected 2026-10-22: the Ollama store on this box turned out to be empty at the start of Phase 0 — all four models were pulled again during Phase 0.]**
