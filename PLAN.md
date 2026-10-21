# PLAN — Sloth Drawer

> Offline agent that reads the manuals you already own and prints one maintenance card per device.
> Hacktoberfest 2026 — DEV Challenge Week 3: "Slow and Steady".

**Hard deadline: 2026-10-25 23:59 PDT = 2026-10-26T06:59:00Z** (DEV API clock is official).
**Budget: 4 days, ~20 focused hours.**

---

## 1. The one-line pitch

You own 40 things. Each came with a manual. You cannot find the manual when the thing starts blinking,
and nobody remembers the filter is due every 2 months. **Sloth Drawer** reads the manual PDFs you already
downloaded, finds the maintenance intervals, quotes the page, and prints **one card per device** you can
tape to the thing. Everything runs on your machine, offline, for free.

---

## 2. Why this wins (research summary, 2026-10-21)

| Finding | Evidence |
|---|---|
| 206 Week-3 submissions existed by Oct 21, arriving at ~90–100/day → projected pool **~600** | DEV API crawl of 3,045 `#hf26challenge` posts |
| File-organizer / paper-summarizer / chat-digest / GitHub-issue are **saturated** (23 / 22 / 15 / 17 entries) | title frequency over 206 Week-3 posts |
| **Device manuals, warranties, maintenance schedules: 0 of 206** | title frequency over 206 Week-3 posts |
| **Partner categories are near-empty**: TabPFN 0, Tinker 0, Arduino 0, DigitalOcean 0, Render 0, Sentry 0, Entire 0, Temporal 0, MongoDB 0, .tech 0, Tiger Data 1, Gemma 13 | tag counts over 206 Week-3 posts |
| Last week's winners were all **narrow, tangible, physical, one hard number** | Week 1 winners post (devteam) |
| Judges rewarded **"the model points, the code checks"** and **honest failure reporting** | highest-reaction Week-3 posts |

**Strategy:** do not chase the overall $250 against 600 entries. Enter 4–6 partner categories where the
field is 0–1. Make the *verification design*, the *model benchmark* and the *swappable retrieval
backend* the memorable parts of the post.

**The two-backend story (this is what makes the Tiger Data category land without breaking the thesis).**
The tool ships with **two retrieval backends behind one interface**:

- **`local`** — SQLite FTS5 with the `trigram` tokenizer. Zero configuration, zero network, works on a
  plane. Matches part numbers like `DX-CF14` that embeddings flatten into surrounding prose.
- **`tiger`** — pgvector + `pg_textsearch` BM25, fused with Reciprocal Rank Fusion, on Tiger Cloud.
  Finds the paraphrases and rare words the keyword index misses.

Both produce the **same card**, and the verifier is what makes either one trustworthy. The cloud backend
is an *enhancement*, never a prerequisite — and only manual text and embeddings ever cross the wire.
No device names, no serial numbers, no purchase dates, no service history.

**Target categories**

| Category | Prize | Why it applies | Effort |
|---|---|---|---|
| Best Use of Gemma | $200 | `gemma3:270m` triage + `gemma3:1b` extractor | 0 (already the stack) |
| Best Use of Render | $200 | deploy the web UI | ~1.5 h |
| Best Use of Sentry Agent Tracing | $100 | per-stage spans, latency, tokens, cost | ~1.5 h |
| Best Use of Entire | $100 | embed the DevRelay agent session | ~0.5 h |
| Best Use of a .tech Domain | $100 | free first-year domain → the live demo | ~0.5 h |
| Best Use of Tiger Data | $100 | **pgvector + `pg_textsearch` hybrid index over manual chunks on Tiger Cloud** | ~2 h |
| Best Use of TabPFN | $200 | forecast filter-replacement spend from your own history | ~2 h (stretch) |

You can only win once per challenge. Enter the categories you genuinely use.

---

## 3. The three design decisions the benchmark forced

Measured on the target box: **4 cores, 7.5 GB RAM, no GPU, Ollama 0.40.6, CachyOS**.

### 3.1 One fact per call, flat schema — never an array

Benchmarked on a synthetic manual page containing 4 intervals
(`bench/final.py`, `bench/bench2.py`):

| Model | Size | Array-of-objects schema | One-fact-per-call schema | Latency | tok/s |
|---|---|---|---|---|---|
| `gemma3:270m` | 291 MB | — | ❌ wrong (claimed 1 month, cited a sentence with no interval) → **validator caught it** | 3.0–6.8 s | 9–16 |
| **`gemma3:1b`** | **806 MB** | ✅ 3/3 intervals, all quotes valid | ✅ PASS | **12–13 s** | 4.7–13.4 |
| `phi4-mini` | 2.5 GB | ❌ returned `{"intervals": []}` — schema-valid, semantically empty | ✅ PASS | 27–48 s | 1.4–3.5 |

`phi4-mini` works but is **2.2–3.8× slower** and **3× the RAM**; with only ~2.9 GB free it swaps
(measured 1.4 GB in swap, 40 s cold starts). A flat `has_interval / task / interval_months / quote / section`
schema, asked **once per chunk**, works on every model tested.

### 3.2 The model points, the code quotes, the code recomputes

The model returns a *quote fragment* (often useless: `"every 2 months"`). Code then:

1. locates the fragment in the source page text,
2. expands it to the enclosing sentence,
3. **re-parses the interval from that sentence**,
4. compares to the model's number → `PASS` / `REPAIR` / `REJECT`.

Verified behaviour on all failure modes:

| Model output | Verdict |
|---|---|
| hallucinated quote (`"...every 6 months"`) | **REJECT** — quote not in page |
| real quote, wrong number (model 3, text 2) | **REPAIR** — code value wins, disagreement recorded |
| cites a sentence containing no interval | **REJECT** — no interval in cited sentence |
| `gemma3:270m`: months=1, cited *"Do not wash the Pre-Carbon filter."* | **REJECT** — caught automatically |

This is the product. Fail-closed, no hallucinated dates, and a measured accuracy number instead of a claim.

### 3.3 Scope cut: "last done", never "bought on"

Nobody remembers when they bought the filter. They remember they cleaned it last month.
`next_due = last_done + interval_months` — one line, no recurrence parsing, no purchase-date fallback,
no `"or every 2 months"` / `"720 hours"` special cases. This is the single biggest build-time saving.

### 3.4 Three-tier cascade (the "conserve your energy" theme, literally)

1. **Regex pre-filter** — free, deterministic. `/every\s+\d+\s+(day|week|month|year)/i` and friends.
   Removes ~80 % of chunks at zero cost.
2. **`gemma3:270m` (291 MB) triage** — yes/no: "does this chunk state an interval?" 3 s/chunk.
3. **`gemma3:1b` (806 MB) extractor** — one fact per call, on triage survivors only. 12 s each.
4. **`phi4-mini` (2.5 GB)** — documented alternative behind `--model`. Measured, not hand-waved.

---

## 4. Day-by-day plan

### Fri Oct 23 — Engine (≈6 h)
- **45 min** Collect 10–12 **text-based** manuals in **one device class** (air purifiers / robot vacuums /
  coffee machines). One class = one card layout = a coherent demo. Note any scanned manuals and skip them
  honestly ("4 manuals skipped: image-only, no text layer").
- **1 h** Scaffold: `pyproject.toml`, `src/sloth_drawer/`, `config.py` model registry, SQLite schema.
- **1.5 h** `corpus/ingest.py` (pypdf → pages), `corpus/chunk.py` (page → chunks carrying page no +
  section heading), `corpus/prefilter.py` (regex candidate scoring).
- **1.5 h** `extract/prompts.py` + `extract/extractor.py` + `extract/verify.py` (the validator).
- **1 h** Test on 5 manuals; every extracted interval must pass the validator or be rejected.

**Exit:** `sloth-drawer scan data/manuals` prints candidate intervals with verified page citations.

### Sat Oct 24 — Cards, state, report (≈6 h)
- **1.5 h** `storage/db.py` (sqlite3, stdlib only) + `storage/service_log.py` (`last_done` → `next_due`).
- **1.5 h** `render/theme.py` + `render/card_html.py` (A6 print card) + `render/card_text.py` (terminal card).
- **1 h** `report/build.py` → `report.json` + `report.md` accuracy table.
- **1 h** Batch runner + CLI (`scan`, `card`, `done`, `report`).
- **1 h** Sentry tracing (`sentry-sdk`, one transaction per manual, a span per stage).
- **2 h** **Retrieval layer** — `retrieval/local.py` (SQLite FTS5, trigram) and `retrieval/tiger.py`
  (pgvector + BM25 + RRF) + `vector/schema.sql`. **Tiger Cloud setup:** `tiger auth login` (the token
  is expired) → `tiger db uri` → `CREATE EXTENSION` → index the corpus. Use a dev service or schema;
  never point DDL at a `read_only: prod` service.

**Exit:** `sloth-drawer report` prints the table that goes in the post:
*"N manuals · M intervals found · K hand-checked correct · L rejected · R repaired · Xs/manual · $0"*.

### Sun Oct 25 — Surface, deploy, write (≈7 h)
- **1.5 h** FastAPI web UI (one page) — core dependency, but the **last** thing built.
- **1 h** Deploy to Render; claim the free `.tech` domain; point it at the demo.
- **1 h** Record the demo (terminal + card + report). One take, no fluff.
- **2.5 h** Write the post. **Writing Quality is the most heavily weighted criterion** — leave it alone
  until the code is frozen.
- **0.5 h** Save the agent session via DevRelay, make it **public**, embed with the `agent_session` tag.
- **0.5 h** `create_article` → review → **publish** (never publish without explicit approval).

**Exit:** post published before 2026-10-26T06:59:00Z, with ≥4 partner categories claimed.

---

## 5. Post outline (pre-filled so the write-up is fast)

1. **Hook** — one concrete number and one human moment.
   *"I own 11 devices. I could not tell you when any of them last needed cleaning. A 291 MB model got it
   wrong, and my verifier caught it."*
2. **What I Built** — the card, the pipeline, the file tree.
3. **Demo** — screenshot of a card + the terminal run + the report table.
4. **How I Built It** — the three-tier cascade, the schemas, the validator.
5. **The validator is the product** — the rejection table from §3.2, verbatim.
6. **The benchmark** — the table from §3.1, including the 270M failure and `phi4-mini` timing.
7. **Why Open Innovation Matters** — concrete, not generic:
   - your manual folder + serial numbers + purchase dates = a map of your home; a closed API stores it;
   - it must work in a basement, a garage, an air-gapped corporate network — **proved, not asserted**:
     the offline run in Phase 3;
   - $0 per run forever, no key, no quota, no vendor deprecation;
   - **swappable model**: `--model phi4-mini` — the "change how your agent behaves" line from the prompt;
   - **swappable retrieval**: the same card from a local SQLite FTS5 index or a Tiger Cloud pgvector
     index — the "let you change how it works" line, in a second dimension;
   - your source text never leaves the machine by default; the validator's verbatim-substring check means
     the model can only ever point at text you already have;
   - **the cloud boundary is a schema constraint, not a promise**: the `manual_chunks` table has no
     column that could hold a serial number, and the code that writes it never sees one.
8. **The Lazy Payoff** — quantify. *"≈20 minutes of manual reading per device, replaced by a 12-second
   extraction and a card. 11 devices, 34 intervals, 0 recurring cost."*
9. **My Agent Session** — DevRelay embed.
10. **Prize Categories** — list by name.
11. **What it got wrong** — the honest section. The 270M failure, the 3 off-by-one intervals, the 4
    scanned manuals you skipped. This is what the highest-reaction posts did.

---

## 6. Risk register

| Risk | Likelihood | Impact | Mitigation | Trigger to act |
|---|---|---|---|---|
| Tiger Cloud service is `read_only: prod` and the app needs DDL | High | Medium | Create a **separate dev service or schema** for the app. The app's DSN is `SLOTH_DATABASE_URL` | Before any `CREATE EXTENSION` |
| `tiger auth login` token expired (it is, right now) | Certain | Low | Run `tiger auth login`, then `tiger db uri` to fetch the service URL | Phase 0 |
| `pg_textsearch` unavailable on the service (needs PG 17/18) | Medium | Medium | Fall back to plain `ts_rank_cd` over a `tsvector` column, or to the local backend | At `CREATE EXTENSION` time |
| Network dies mid-run with the tiger backend | Medium | Low | The run is per-manual and resumable; the local backend needs no network at all | — |
| Scanned / image-only manuals | High | Medium | Pre-check text layer; skip + record `no_text_layer`; say so in the post | If <8 usable manuals by Fri 18:00, switch device class |
| `gemma3:1b` too weak on some manuals | Medium | High | Switch extractor to `phi4-mini` (same interface, slower but passed every test) | If hand-checked accuracy <80 % by Sat 12:00 |
| `phi4-mini` swapping / OOM | Medium | Low | Default to `gemma3:1b` (806 MB); `keep_alive: 0` to unload | — |
| Corpus not ready | Medium | High | Fri 09:00 hard checkpoint; fall back to a narrower demo (6 devices) | Fri 18:00 |
| Post not written | Low | Critical | Write the report table first (it *is* the post data) | — |
| Miss the deadline | Low | Critical | Publish a draft by Sun 18:00, revise after | Sun 18:00 |
| "Just another RAG app" | Medium | High | Lead with the verifier, the benchmark and the card — not with retrieval | — |

---

## 7. Definition of done

- [ ] `sloth-drawer scan <dir>` runs a full corpus offline with the Wi-Fi off, on CPU only
- [ ] The local FTS5 backend and the Tiger Cloud backend produce the **same card** for the same manual
- [ ] The Tiger Cloud `manual_chunks` table contains no device name, serial number or date
- [ ] Every emitted interval has a page citation the code verified as a verbatim substring
- [ ] Zero model-authored dates — all dates computed in `storage/cards.py`
- [ ] `report.md` contains the accuracy table
- [ ] Card renders as HTML (print-ready A6) and as text
- [ ] Sentry trace screenshot captured
- [ ] Demo recorded
- [ ] Agent session saved, public, embedded
- [ ] Post published with ≥4 partner categories claimed, before 2026-10-26T06:59:00Z
