# Instructions — setting up and using Sloth Drawer

> The short version lives in `README.md` (60-second quickstart). This file is the complete
> setup and day-to-day guide: what to install, where the PDFs go, which models to pull and
> which to trust, every command with its flags, what lands on disk, and what to do when
> something fails.

---

## 0. What you need before anything

| Thing | Why | Check |
|---|---|---|
| **Python 3.11+** | the tool is a Python package (`pyproject.toml` says `>=3.11`) | `python3 --version` |
| **[uv](https://docs.astral.sh/uv/)** | installs dependencies in seconds and runs the CLI | `uv --version` |
| **[Ollama](https://ollama.com/) ≥ 0.40** | runs the models locally; nothing is called in the cloud | `ollama --version` |
| A 4-core CPU box with ~3 GB free RAM | that is the whole reference box; no GPU, ever | `free -h` |

Install Ollama once, then leave `ollama serve` running (it usually runs as a service;
if not: `ollama serve &`). Everything else is one `uv sync`.

## 1. Models: pull *this* one, and know why

```sh
ollama pull gemma3:1b      # REQUIRED — the default extractor
```

`gemma3:1b` (806 MB) is the **extractor** and the model this project is tuned around.
Measured on the reference box (4 cores, no GPU): it found every ground-truth interval on
the benchmark page at **9.1 s per interval** and passed verification; `gemma3:270m`
**failed the extraction task** (it cited a sentence with no interval in it), so it is only
used as an *optional* yes/no gate.

```sh
ollama pull gemma3:270m        # OPTIONAL — only for --triage; never as an extractor
ollama pull phi4-mini          # OPTIONAL — the measured fallback (--model phi4-mini)
ollama pull nomic-embed-text   # OPTIONAL — only needed for the Tiger Cloud index
```

| Model | Role | When | Measured |
|---|---|---|---|
| `gemma3:1b` (806 MB) | extractor — **default** | always | 9.1 s/interval, PASS |
| `gemma3:270m` (291 MB) | optional triage gate (`--triage`) | opt-in | 3.6 s, **REJECT — fails extraction** |
| `phi4-mini` (2.5 GB) | alternative extractor (`--model phi4-mini`) | fallback | 53.9 s, PASS — 6× slower, 3× the RAM, uses swap |
| `nomic-embed-text` (274 MB) | embeddings for `sloth-drawer index` | only for the Tiger backend | — |

Sanity-check the registry any time: `uv run sloth-drawer models`.
Without Ollama reachable, **every model-dependent command exits 2** with
`Cannot reach Ollama at http://localhost:11434. Start it with "ollama serve".` — that is
by design, not a bug.

## 2. Install the tool

```sh
git clone https://github.com/Gaurav5189/sloth-drawer && cd sloth-drawer
uv sync                     # dev group included (pytest, etc.)
# or, runtime only:        uv sync --no-group dev
```

**Important: on a checkout, every command is `uv run sloth-drawer …`,** not bare
`sloth-drawer`. The bare command only exists after a real install (`uv tool install .`
or `pipx install .`). When a shell says `command not found: sloth-drawer`, it has not
been installed — use `uv run` or install it. All README and post examples assume
`uv run` in a checkout.

Core install is deliberately tiny: `pypdf` + FastAPI + uvicorn + psycopg + pgvector,
~3.7 s cold with an empty uv cache.

## 3. Where the PDFs go

- **Folder:** `data/manuals/` is the shipped example, but `sloth-drawer scan` takes any
  directory path as its argument — put your PDFs wherever you like and pass the folder.
- **Text-based PDFs only.** A scanned image-only manual has no text layer; it will be
  **skipped loudly** (`NoTextLayerError`) and recorded in the report, never silently
  dropped. Provide your own OCR pass for those — this tool intentionally does not OCR.
- **Register every manual in `data/devices.toml`.** One `[[device]]` block per physical
  thing:

  ```toml
  [[device]]
  slug       = "coway-airmega-100"       # used in card/done/serve URLs — kebab-case
  name       = "Coway Airmega 100"       # printed on the card
  manufacturer = "Coway"                  # optional
  model      = "Airmega 100"              # optional
  category   = "air-purifier"             # optional
  manual     = "coway-airmega-100.pdf"    # filename inside the scan directory
  ```

  The scan **refuses to start** without this registry
  (`Device registry not found: …. Create it with one [[device]] block per manual`) —
  the model never names a device; the human does. A manual that *fails to read* still
  registers its device row, so `card` prints the explicit "interval not found" card
  instead of claiming the device was never seen.
- Where your manuals came from is worth recording in `data/corpus_sources.md`, so a
  later re-scan remembers which vendors just serve a viewer page.

## 4. Run it

Insert `uv run` before every command below (see §2).

### Scan the corpus (the one long command)

```sh
uv run sloth-drawer scan data/manuals            # full corpus, unattended
uv run sloth-drawer scan data/manuals --resume   # finish a run that died (skips completed manuals; ~3 s when done)
uv run sloth-drawer scan data/manuals --list     # also print every accepted interval + its page citation
uv run sloth-drawer scan data/manuals --no-persist  # dry run — writes no DB rows, no report
```

Useful knobs (defaults are the measured best):

| Flag | Default | Meaning |
|---|---|---|
| `--model` | `gemma3:1b` | extraction model; `phi4-mini` is the measured fallback |
| `--triage` | off | gate candidates through `gemma3:270m` first (off by default: the pre-filter already does most of that job for free) |
| `--threshold` | `2` | pre-filter score a chunk must reach to reach a model |
| `--keep-alive` | model default | how long Ollama holds the model in RAM (e.g. `5m`, `0` to unload) |
| `--force` | default | start fresh, ignoring any checkpoint |
| `--no-persist` | off | dry run, still prints the report |

Expect **~30 s per manual** on the reference box (one model call per interval-shaped
sentence); a 19-manual corpus is ~10 minutes. Each manual is its own SQLite transaction
and checkpoint row (`out/batch.json`, keyed by the PDF's SHA-256), so a kill at manual 18
keeps the first 17 (`--resume`).

### Read one card

```sh
uv run sloth-drawer card honeywell-hpa3000          # colour terminal card + A6 HTML
uv run sloth-drawer card honeywell-hpa3000 --ascii  # pure-ASCII terminal card
uv run sloth-drawer card honeywell-hpa3000 --no-color
```

A device with nothing verified prints the explicit **"interval not found"** card — never
a blank.

### Log that you did a task (the date is computed, never stored)

```sh
uv run sloth-drawer done honeywell-hpa3000 "Filter Replacement"
uv run sloth-drawer done honeywell-hpa3000 "Filter Replacement" --note "vacuumed housing"
```

`next_due = last_done + interval_months` is computed **at read time in code**. A task
never logged shows "no service recorded" — the card never invents a date.

### The report

```sh
uv run sloth-drawer report            # the accuracy table: found / PASS / REPAIR / REJECT
uv run sloth-drawer report --json     # the machine-readable version
```

Read the verdicts like this: **PASS** = the model's number matched the code's re-parse of
the cited sentence; **REPAIR** = the sentence contained a real interval but the model got
the number wrong — the code's value went on the card, the disagreement is printed; **REJECT**
= the model's answer could not be traced back to the page (hallucinated quote, no interval
in the cited sentence, or an invented task label) and it appears nowhere.

### The web UI

```sh
uv run sloth-drawer serve             # http://127.0.0.1:8000
uv run sloth-drawer serve --port 8123
```

Device list → card with verbatim quotes and computed due dates → *Mark done*. The card
route is byte-identical to the CLI card (a test proves it). Note the public demo at
https://sloth-drawer.onrender.com/ serves a committed snapshot, and its *Mark done*
writes shared demo state — on a live deployment anyone can move dates by design of the
demo (state resets from the seed on redeploy).

## 5. What lands on disk

| Path | What |
|---|---|
| `out/sloth.db` | SQLite state: devices, verified intervals, service log, runs (WAL) |
| `out/batch.json` | the resumable checkpoint (per-manual SHA-256 → summary) |
| `out/report.md` / `out/report.json` | the accuracy report (the post table) |
| `out/cards/<slug>.html` | the print-ready A6 card files |
| `vector/schema.sql`, `retrieval/local.py` | the two index definitions |
| `out/*.txt` | the shipped evidence logs: full run, offline proof, benchmark, parity |

## 6. Optional: the Tiger Cloud retrieval backend

The default retrieval index is **local SQLite FTS5** — zero config, offline, matches part
numbers like `DX-CF14` via the trigram tokenizer. The **Tiger backend** (pgvector +
`pg_textsearch` BM25, fused with RRF) is opt-in and only changes *retrieval*, never the
cards:

```sh
export SLOTH_DATABASE_URL="postgresql://user:pass@host:5432/db"   # a DEV service/schema — it needs DDL
uv run sloth-drawer index data/manuals   # chunk → embed → upsert (needs nomic-embed-text pulled)
uv run sloth-drawer report               # a run row now records backend "tiger"
```

Only **manual chunk text and embeddings** are written — the `manual_chunks` table has no
column that could hold a device name, serial number, purchase date or service log, and
the code that writes it never sees one. Unset the DSN and you are offline again.

## 7. When something fails

| Symptom | Meaning | Fix |
|---|---|---|
| `command not found: sloth-drawer` | not installed / running from a checkout | use `uv run sloth-drawer …`, or `uv tool install .` |
| `Cannot reach Ollama at http://localhost:11434…` | nothing is listening | `ollama serve` (or start the service) |
| `ollama pull gemma3:1b` printed by a scan | model not pulled yet | run the pull it suggests |
| `Device registry not found: …` | no `data/devices.toml` | create it, one `[[device]]` per manual (§3) |
| `skipped <file>: … no text layer` (warning + skip row) | image-only scan PDF | skip honestly; OCR yourself or find a text PDF |
| Card says "interval not found" | device registered, nothing verified for it | normal — a verifier REJECT is a *missing* card, never a wrong one |
| `MODEL SAID X · SOURCE SAYS Y` lines in the scan output | REPAIRs working | the code's value went on the card; the disagreement is printed, not hidden |
| `function to_bm25query(unknown) does not exist` | bare-literal BM25 call | always the two-argument form with the schema-qualified index name (developer trap, documented in `MEMORY.md`) |

## 8. The two rules worth repeating

1. **The model points, the code quotes, the code recomputes.** A model failure can lose
   a card; it can never put a wrong date on one.
2. **Everything works with the network off.** Try it:
   `unshare -rn` (or just switch Wi-Fi off) and run the same scan — the shipped offline
   proof is `out/scan-offline.txt`. The Tiger backend is an enhancement, never a
   prerequisite.
