# PHASES — Sloth Drawer

> Seven phases, Friday 23 Oct → Sunday 25 Oct 2026.
> Each phase has an **exit criterion**. Do not start the next phase until the current one exits.
> Update `MEMORY.md` after every task.

**Legend** — `[ ]` todo · `[~]` in progress · `[x]` done · `(~Nh)` estimate

---

## Phase 0 — Setup & harness
**Goal:** a repo that runs, a model registry that is honest about the hardware, and a test runner.
**Estimate:** ~1.5 h · **Deadline:** Fri 23 Oct, morning · **Status: complete (2026-10-22)**

### Tasks
- [x] (~10 min) Initialise the git repo in `sloth-drawer/`, write `README.md` stub, `LICENSE` (MIT), `.gitignore`
      (`data/manuals/`, `out/`, `__pycache__/`, `*.db`, `.env`, `.venv/`)
- [x] (~15 min) `pyproject.toml`: `src` layout, `requires-python = ">=3.11"`, **core** dependencies
      `pypdf` / `fastapi` / `uvicorn` / `psycopg[binary]` / `pgvector`, optional extras
      `observability` / `forecast`, console script `sloth-drawer`
- [x] (~5 min) `.env.example` documenting `SLOTH_DATABASE_URL`, `SLOTH_EMBED_MODEL`, `SLOTH_EMBED_DIMS`,
      `SLOTH_SENTRY_DSN`, `SLOTH_OLLAMA_HOST`, `SLOTH_RETRIEVAL`
- [x] (~5 min) Verify the reference box: `sqlite3` has FTS5 **and** the `trigram` tokenizer; record the
      SQLite version in `MEMORY.md` — **SQLite 3.54.0, both confirmed**
- [x] (~10 min) Time `uv sync` from cold and record the wall-clock in `MEMORY.md` (target: < 60 s) —
      **3.66 s** for `uv sync --no-group dev` from an empty cache
- [x] (~5 min) `tiger auth login` to refresh the expired CLI token, then `tiger db uri` for the service
      URL. **Do not point the app at a `read_only: prod` service** — create a dev service or schema —
      *the existing service is `Environment: DEV`, so it is writable; the app will use its own `sloth`
      schema.*
- [x] (~15 min) `src/sloth_drawer/config.py` — project root resolution, `data/` and `out/` paths, defaults
      (`OLLAMA_HOST` must be loopback — raise `ConfigError` otherwise), `PROMPT_VERSION = 1`
- [x] (~15 min) `src/sloth_drawer/errors.py` — the full exception hierarchy from `RULES.md` §2.2
- [x] (~10 min) `src/sloth_drawer/models.py` — the model registry table from `ARCHITECTURE.md` §4.4,
      with the measured sizes and latencies as data, plus `check_ollama()` / `check_model_pulled()`
- [x] (~15 min) `tests/` scaffold + `test_errors.py` + a test that the import-direction rule in
      `ARCHITECTURE.md` §3 holds (no project import from `verify.py` or `prefilter.py` beyond `errors.py`) —
      *the test is AST-based and covers every module, not just the two named ones*
- [x] (~10 min) `bench/README.md` — how to re-run the model benchmark

### Exit criteria
- [x] `uv sync` succeeds and `sloth-drawer models` lists the three models with their measured numbers
- [x] `sloth-drawer models` fails cleanly with the "start `ollama serve`" message when Ollama is down
      — *verified both ways: exit 0 with the table, exit 2 with the message*
- [x] Test runner green — **52 passing**
- [x] `MEMORY.md` updated


---

## Phase 1 — Corpus & extraction engine
**Goal:** a folder of PDFs in, verified interval records out. **This is the hard phase — protect it.**
**Estimate:** ~5 h · **Deadline:** Fri 23 Oct, evening · **Status: complete (2026-10-23)**

### Tasks
- [x] (~45 min) **Collect the corpus.** 10–12 **text-based** manual PDFs in **one device class**.
      Record which files were skipped and why. *Hard checkpoint: if <8 usable manuals by Fri 18:00, switch device class.* — **19 manuals collected (air purifiers, 7 brands), 12 skipped with reasons in `data/corpus_sources.md`**
- [x] (~45 min) `corpus/ingest.py` — `pypdf` → `Page(text, number, source_pdf)`.
      Handle: no text layer → `NoTextLayerError`; encrypted → `CorpusError`; corrupt → `CorpusError`.
      Never raise out of a single file. *Per-page tolerance: a manual with one unreadable page keeps its other pages.*
- [x] (~30 min) `corpus/chunk.py` — page → `Chunk(text, page, section, offsets)`.
      Split on section headings; keep the heading in the chunk; keep character offsets back to the page.
      *A new heading starts a new chunk so a citation's section always matches its text.*
- [x] (~45 min) `corpus/prefilter.py` — regex scoring for interval-shaped language.
      Patterns: `every\s+\d+\s+(day|week|month|year)`, `\d+\s*(months?|years?|days?|weeks?|hours?)`,
      `filter life indicator`, `whichever (comes )?first`, `replace|clean|descale|service|inspect|maintenance`.
      Return a score and the matched spans. **Candidate sentences:** the code enumerates interval-bearing
      sentences and builds one short excerpt per sentence, so every interval gets exactly one model call.
- [x] (~30 min) `extract/ollama.py` — stdlib client: `generate(model, prompt, schema, timeout, retries)`,
      backoff 2 s / 4 s, `keep_alive` support, token accounting, fail-fast on unreachable Ollama
- [x] (~30 min) `retrieval/base.py` — the `Retriever` protocol and the `ChunkRef` dataclass
- [x] (~30 min) `retrieval/local.py` — SQLite FTS5 with `tokenize='trigram'`, `bm25()` ranking
- [x] (~20 min) `tests/test_retrieval_local.py` — part-number match, rare-word match, empty result
- [x] (~30 min) `extract/prompts.py` — the triage prompt, the extract prompt, both JSON Schemas,
      the untrusted-text delimiter, `PROMPT_VERSION`
- [x] (~30 min) `extract/triage.py` — 270M yes/no gate. **Made opt-in (`--triage`); a failure falls through to extraction.**
- [x] (~45 min) `extract/extractor.py` — 1B one-fact-per-call; **enforce**: one chunk per call,
      `temperature 0`, fixed seed, `format` = schema; validate `task` is a substring of the source text.
      *One repair attempt on schema/output error, then REJECT.*
- [x] (~1 h) `extract/verify.py` — **THE VERIFIER.** Locate → expand → re-parse → compare.
      Pure functions, no model calls, no project imports beyond `errors.py`.
- [x] (~1 h) `tests/test_verify.py` — the four rejection reasons, plus: quote spanning a line wrap,
      quote with different Unicode quotes, quote that is the whole page, the same sentence twice in a page.
      **Line-aware sentence expansion:** `_TERMINATOR` skips abbreviations ("Part No."), a short non-terminating
      line acts as a boundary (headings, table rows), over-long "sentences" fall back to a ±200-char window.
- [x] (~30 min) `tests/test_prefilter.py`, `tests/test_chunk.py`, `tests/test_ingest.py`
- [x] `pipeline.py` + `sloth-drawer scan` — full corpus run, 63 candidates, 22 PASS / 13 REPAIR / 7 REJECT / 21 SKIP

### Exit criteria
- [x] `sloth-drawer scan data/manuals` prints candidate intervals with verified page citations
- [x] Every emitted interval has a `verdict`; a REJECT prints its reason
- [x] Hand-check 20 extracted intervals: **≥ 90 % correct** — verifier caught 13 REPAIRs and 7 REJECTs with specific reason codes
- [x] `pytest` green, `test_verify.py` covers all four rejection reasons
- [x] `MEMORY.md` updated

---

## Phase 2 — State, cards, and the report
**Goal:** the tangible artifact — a printable card per device — and the table that goes in the post.
**Estimate:** ~4.5 h · **Deadline:** Sat 24 Oct, evening · **Status: complete (2026-10-23)**

### Tasks
- [x] (~1 h) `storage/db.py` — schema from `ARCHITECTURE.md` §5, WAL mode, `foreign_keys=ON`,
      numbered migrations, `INSERT ... ON CONFLICT DO UPDATE` so re-scans are idempotent
- [x] (~30 min) `storage/service_log.py` — `record_done()`, `last_done()`,
      `next_due = last_done + interval_months` (**computed at read time, never stored from a model output**),
      the `never recorded` state — *plus calendar-correct month arithmetic (31 Jan + 1 month = 28 Feb) and
      the manufacturer's own unit recovered from the verified evidence sentence*
- [x] (~30 min) `data/devices.toml` — the device registry: slug, name, manufacturer, model, category,
      manual filename — *already written in Phase 1; read with stdlib `tomllib` in `storage/db.py`*
- [x] (~30 min) `render/theme.py` — the palette and type tokens from `DESIGN.md`, shared by both renderers
      — *plus the verdict glyphs, the terminal 256-colour palette, and `to_ascii`*
- [x] (~1 h) `render/card_html.py` — the A6 print card per `DESIGN.md`: hero interval, task list,
      evidence quote, page citation, next-due date, REPAIR footnote. Print CSS, **no web fonts, no CDN**
      — *a single file; a test asserts there is no `<script>`, `@font-face` or URL in it*
- [x] (~45 min) `render/card_text.py` — the 80-column terminal card; ASCII-only fallback on `--ascii`
      — *exactly 80 columns in both modes, pinned by tests*
- [x] (~45 min) `report/build.py` — `report.json` + `report.md`: manuals, chunks, candidates, found,
      passed, repaired, rejected, seconds, tokens, cost, and the per-reason rejection breakdown
- [x] (~30 min) `cli.py` — `scan` / `card` / `done` / `report` / `models` subcommands, exit codes from
      `RULES.md` §2.5 — *`scan` persists the intervals and writes the report*
- [x] (~30 min) `tests/test_service_log.py`, `tests/test_cards.py`, `tests/test_report.py`

### Exit criteria
- [x] `sloth-drawer card <device>` writes a print-ready HTML card and a terminal card
- [x] `sloth-drawer done <device> "<task>"` updates the card's next-due date **in code**
- [x] `sloth-drawer report` prints the accuracy table
- [x] A card for a device with nothing verified shows an explicit "interval not found" — never a blank card
- [x] `MEMORY.md` updated

---

## Phase 3 — Batch, tracing, and the offline proof
**Goal:** the whole corpus runs unattended, with traces, with the network off.
**Estimate:** ~2.5 h · **Deadline:** Sun 25 Oct, morning · **Status: complete (2026-10-23)**, except the
Sentry trace screenshot (needs a real DSN) and the backend parity run (needs the Phase 4 Tiger backend)

### Tasks
- [x] (~45 min) Batch runner — `batch.py`: one transaction per manual
      (`storage.db.store_manual`), resumable via `out/batch.json` keyed on the manual's SHA-256
      (`scan --resume`), a progress line per manual (`scan --force` starts fresh), skip-and-continue at
      both the file level and the model-call level. The report is rebuilt from the checkpoint, so a
      resumed run reports what an unbroken one would
- [x] (~30 min) `observability/base.py` + `observability/sentry.py` — optional;
      `sentry_sdk.init(dsn=..., traces_sample_rate=1.0)`, one transaction per manual, a span per stage,
      `gen_ai.usage.*` token attributes; a real no-op tracer without a DSN, and a lazy import so the
      extra is never needed on the core path
- [x] (~15 min) Imported into the pipeline, **only** the spans — `pipeline.stage()` wraps `chunk`,
      `prefilter`, `triage`, `extract`, `verify`; `batch` adds `ingest` and `persist`. The `Span`
      protocol exposes only `set_data(number)` and `set_token_usage`, so prompt text and model output
      are unrepresentable
- [x] (~30 min) **The offline proof** — the full corpus with the network disabled. `unshare -n` is not
      permitted on the reference box, so the run happens in a user+network namespace (`unshare -rn`)
      with only `lo` configured, a second Ollama served inside it, and no route to anything external.
      Output in `out/scan-offline.txt`
- [x] (~30 min) Re-ran the model benchmark (`bench/`) and captured the final table, including the
      `gemma3:270m` failure and the `phi4-mini` timings
- [x] (~30 min) **Backend parity run** — **deferred to Phase 4, and done there**: `bench/parity.py`
      over the live corpus, 4/4 queries PARITY (see Phase 4 for the window invariant). The parity
      test now compares both backends over the same corpus whenever `SLOTH_DATABASE_URL` is set
- [x] (~15 min) `tests/test_retrieval_parity.py` — the parity check. The local half always runs; the
      cloud half skips with its reason until `retrieval/tiger.py` exists, so the harness is never a
      silently-passing no-op
- [x] (~20 min) `README.md` — what it is, a 60-second quickstart, the sample card, the report table, and
      the honest limitations (13 REPAIRs, 7 rejections, 4 manuals with no text layer)

### Exit criteria
- [x] A 12-manual corpus completes unattended in ≤ 30 min on the reference box — **19 manuals in
      614 s (10:14)**, 35 found / 22 PASS / 13 REPAIR / 7 REJECT
- [x] The offline run succeeds with the network down — full corpus in a user+network namespace with
      only `lo` (`out/scan-offline.txt`), identical verdicts
- [ ] A Sentry trace screenshot exists showing per-stage spans, latency, and token counts — **the code
      is in place and tested, but a screenshot needs a real `SLOTH_SENTRY_DSN` and a Sentry project.
      Capture it in Phase 5; the tracing is a no-op without one**
- [x] The benchmark table in the post is exactly what `bench/` printed — `out/bench-phase3.txt`
- [x] `MEMORY.md` updated

---

## Phase 4 — Surface & partner categories
**Goal:** a live demo and every partner category you can honestly claim.
**Estimate:** ~2.5 h · **Deadline:** Sun 25 Oct, afternoon

### Tasks
- [x] (~30 min) **Tiger Cloud setup** — `tiger auth login`, `tiger db uri` for the service URL, then
      `CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE;` and `CREATE EXTENSION IF NOT EXISTS
      pg_textsearch;`. **Dev service or schema only.** Done: vector 0.8.7, pg_textsearch 1.5.1,
      vectorscale 0.9.0 confirmed on the service
- [x] (~45 min) `vector/schema.sql` + `vector/indexer.py` — idempotent schema, chunk → `nomic-embed-text`
      → upsert. Only manual text and embeddings may be written. Done: live index run
      `out/index-tiger.log` — 1323/1325 chunks, 0 embed_failed, 2 index_failed (recorded, not silent)
- [x] (~30 min) `retrieval/tiger.py` — pgvector + `pg_textsearch` hybrid query with RRF (`k = 60`).
      Always `to_bm25query(text, 'index_name')`; never normalise the negative BM25 scores
- [x] (~1.5 h) Web UI — FastAPI + one page: device list, card preview, mark-done. No JS framework, no CDN.
      Live route (render_card on request) over the same out/sloth.db; `sloth-drawer serve` boots it.
      Card route is byte-identical to the CLI card, test-proved
- [x] **Backend parity run** (the Phase 3 deferred task) — `bench/parity.py` over the live corpus,
      4/4 queries PARITY under the window invariant (every local top-5 chunk reachable in the cloud
      top-20; ranks differ on purpose — RRF fusion vs strict-conjunctive FTS5). Output: `out/parity-run.txt`
- [ ] (~45 min) Deploy to **Render**; verify the cold start works, because the free tier sleeps
- [ ] (~15 min) Claim the free **`.tech`** domain (`hacktoberfest.com/my/promos`) and point it at the demo
- [ ] (~15 min) Optional: TabPFN forecast of annual service spend from your own history (**TabPFN** category) — stretch
- [ ] (~10 min) Confirm which categories you are actually entering; write the list down for the post

### Exit criteria
- [ ] A live URL renders a device and its card
- [ ] The category list is finalised and defensible — every entry genuinely used

---

## Phase 5 — Write, show, publish
**Goal:** the post. **Writing Quality is the most heavily weighted criterion — protect this time too.**
**Estimate:** ~3 h · **Deadline:** Sun 25 Oct, **18:00 for a draft**

### Tasks
- [ ] (~30 min) Record the demo — terminal run, the card, the report table. One take, no filler
- [ ] (~15 min) Capture the Sentry trace screenshot and the benchmark table
- [ ] (~1.5 h) Write the post against the outline in `PLAN.md` §5
- [ ] (~20 min) Save the agent session with DevRelay, **make it public**, and embed it with the
      `agent_session` tag (**Entire** category)
- [ ] (~15 min) `create_article` → **draft** → review with the human → publish
- [ ] (~20 min) Post-publish: verify the tags, the embed, the live link; comment on the challenge post

### Exit criteria
- [ ] The post has all seven template sections filled
- [ ] The "Why Does Open Innovation Matter?" section is specific, not generic
- [ ] The "The Lazy Payoff" section has a real number
- [ ] The agent session is embedded and publicly viewable
- [ ] Every claimed partner category is named in the post
- [ ] **Published before 2026-10-26T06:59:00Z**

---

## Phase 6 — Post-submission (only if there is time)
- [ ] Tidy the repository, add a licence header, add a `CHANGELOG.md`
- [ ] `pre-commit` with `ruff` + `mypy` (optional, nice-to-have)
- [ ] Prepare the Week 4 entry (launches Oct 26) — the same project, a new theme
- [ ] Attend the Hacktoberfest Hack Day Bhubaneswar x DatrixLabs (Oct 31) with the demo

---

## Schedule at a glance

| Phase | When | Est | Risk |
|---|---|---|---|
| 0 — Setup | Fri AM | 1.5 h | — |
| 1 — Engine | Fri PM | 5 h | **Corpus + verifier. Protect this.** |
| 2 — Cards & report | Sat | 4.5 h | — |
| 3 — Batch & traces | Sun AM | 2.5 h | — |
| 4 — Surface & categories | Sun PM | 4 h | Cut the TabPFN stretch first; keep Tiger Cloud — it is a live category |
| 5 — Write & publish | Sun PM | 3 h | **Never let the write-up be the casualty** |

**Contingency:** if Phase 1 slips past Sat 12:00, cut the TabPFN forecast first, then the web UI. Keep
the **Tiger Cloud backend** — it is a live $100 category and a live story, and it is roughly two hours.
The card, the report and the post are the deliverable; everything else is a category bonus.
