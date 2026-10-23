# Sloth Drawer

> Offline agent that reads the manual PDFs you already downloaded and prints **one maintenance card
> per device** — the interval, the manufacturer's own sentence, the page number, and the next date it
> is due.

**Status: Phase 3 — a 19-manual air-purifier corpus runs unattended, offline, on the CPU, with a
trace per manual.** `sloth-drawer scan data/manuals` yields **35 intervals found · 22 verified ·
13 repaired · 7 rejected** in ~10 minutes, at **$0**, on a 4-core box with no GPU. The verifier
(`extract/verify.py`) is the product; the report in [`out/report.md`](out/report.md) is the evidence.

## What it is

You own a handful of devices. Each came with a manual. When the thing starts blinking, you cannot find
the manual, and nobody remembers the filter is due every 2 months.

Sloth Drawer reads the manual PDFs already on your disk, finds the maintenance intervals, and quotes the
page they came from. It runs on your machine, with the network off, for free. It ships two retrieval
backends behind one interface — a local SQLite FTS5 index (the default, zero configuration) and a Tiger
Cloud pgvector + BM25 index (opt-in) — and both must produce the same card.

## Design in one line

> **The model points, the code quotes, the code recomputes.**

A ~1B open-weight model (`gemma3:1b`, 806 MB) is only ever allowed to *point at a candidate sentence*.
Code then:

1. locates that sentence in the cited page as a **verbatim substring**,
2. expands it to the enclosing sentence,
3. **re-parses the interval from that sentence**, and
4. compares its own number with the model's → `PASS` / `REPAIR` / `REJECT`.

The code's number wins, and every disagreement is printed rather than hidden. A model failure can
produce a *missing* card; it can never produce a wrong date.

## 60-second quickstart

```bash
# 1. The tool. Core install is a handful of wheels; no framework, no cloud SDK.
git clone https://github.com/sloth-drawer/sloth-drawer && cd sloth-drawer
uv sync

# 2. Local inference. Inference never leaves the machine.
ollama serve &
ollama pull gemma3:1b

# 3. Your corpus: drop the PDFs into data/manuals/ and list them in data/devices.toml.
#    (A registry entry is one [[device]] block; see data/devices.toml for the shape.)

# 4. One command, one card per device.
uv run sloth-drawer scan data/manuals     # read the corpus, verify, store the report
uv run sloth-drawer card medify-ma-40     # print the card and write the A6 HTML
uv run sloth-drawer done medify-ma-40 "Replace filters"   # log it; the due date recomputes
uv run sloth-drawer report                # the accuracy table
uv run sloth-drawer serve                 # the web demo: device list, card, mark-done (127.0.0.1:8000)
```

A scan is **resumable**: each manual is written in its own transaction and checkpointed, so a run that
dies at manual 18 keeps the first seventeen. `sloth-drawer scan data/manuals --resume` picks up where it
stopped. Progress is one line per manual:

```
[  1/19] done    blueair-blue-pure-211a.pdf: 1 candidates, 1P 0C 0R, 8s
[  2/19] done    blueair-health-protect-7300.pdf: 1 candidates, 0P 0C 0R, 10s
[  3/19] done    coway-airmega-100.pdf: 4 candidates, 2P 0C 0R, 42s
...
[ 19/19] done    winix-c610.pdf: 1 candidates, 0P 1C 0R, 7s
```

## Sample output

A terminal card (exactly 80 columns, ASCII fallback with `--ascii`):

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Medify MA-40                                                    AIR PURIFIER │
│ Medify · MA-40                                                               │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ REPLACE EVERY                                                                │
│ 6 months                                                                     │
│                                                                              │
│ Replace filters                                                              │
│ Next due  01 Feb 2027                                                        │
│ ✓ VERIFIED                                                                   │
│                                                                              │
│ ┌──────────────────────────────────────────────────────────────────────────┐ │
│ │ "2. You change the filters with genuine and original Medify Air          │ │
│ │ replacement filters at least once every six (6) months or after 3000     │ │
│ │ hours of use (whichever comes first)."                                   │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│ MANUAL p.12 · LIFETIME WARRANTY                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

The same device also renders as a **print-ready A6 HTML card** — a single file, system fonts only, no
script, no CDN, no web font:

```bash
sloth-drawer card medify-ma-40      # -> out/cards/medify-ma-40.html
```

And the report table that goes in the write-up:

```
19 manuals · 35 intervals found · 22 verified · 13 repaired · 7 rejected · 614s · 22401 tokens · $0.00

Rejection reasons:
  task_not_in_source             7
```

## How it works

```
PDFs ─▶ ingest ─▶ chunk ─▶ prefilter ─▶ [triage] ─▶ extract ─▶ VERIFY ─▶ storage ─▶ card / report
        pypdf    page+    regex        270M        1B         code        sqlite     A6 + text
        → pages  section  (free)       yes/no      one fact   locates,    WAL
                                                 per call   re-parses
```

| Stage | Owner | What it does |
|---|---|---|
| prefilter | **code** | Regex over interval-shaped language; ~80 % of chunks never reach a model |
| triage (optional) | `gemma3:270m` | Yes/no gate. Off by default — the pre-filter already does the work |
| extract | `gemma3:1b` | One fact per call, flat JSON schema, `temperature 0`, fixed seed |
| **verify** | **code** | Locate → expand → re-parse → compare. The part worth 40 unit tests |

**The verifier is fail-closed.** A hallucinated quote, a real quote with the wrong number, or a cited
sentence that contains no interval all resolve to `REJECT`, not to a guess. `--model phi4-mini` swaps in
a slower extractor behind the same interface; the verifier catches the same mistakes.

**Two retrieval backends, one interface.** `local` is SQLite FTS5 with the `trigram` tokenizer — it
matches part numbers such as `DX-CF14` that embeddings flatten into prose, and it needs no network and no
configuration. `tiger` is pgvector + `pg_textsearch` BM25 fused with Reciprocal Rank Fusion on Tiger
Cloud. The backend is chosen in `config.py` and injected; there is no `if backend ==` in the pipeline.

## Honest limitations

- **The model is wrong a lot, and that is the point.** Of 35 intervals the corpus produced, **13 were
  `REPAIR`**: the model named a number that disagreed with the sentence it quoted, and the *code* value
  is the one on the card. The card prints the disagreement (`MODEL SAID 3 · SOURCE SAYS 12`).
- **7 candidates were rejected**, every one because the task label the model returned was not a
  substring of the source text (`task_not_in_source`). Nothing unverified reaches a card.
- **Image-only manuals are skipped, not OCR'd.** The collector found 4 scanned manuals in the candidate
  set; each is recorded with the reason `no_text_layer` and named in the report. Adding an OCR path is
  out of scope for v1.
- **A card is only as good as its manual.** If the manual never states an interval, the card says
  `INTERVAL NOT FOUND` and lists the pages searched — it does not invent one.
- **The corpus is one device class** (air purifiers, 7 brands). The verifier is class-agnostic, but the
  demo is deliberately narrow.
- **`gemma3:1b` is the default because it is fast on a plain laptop**, not because it is the most
  accurate model tested. `phi4-mini` passed the same tests and is 2–4× slower; a machine with ≥ 6 GB
  free gains little from the swap, and a machine with less will swap.

## Documentation

| Document | What it holds |
|---|---|
| [`DOCS/PRD.md`](DOCS/PRD.md) | Problem, users, features, success metrics |
| [`DOCS/ARCHITECTURE.md`](DOCS/ARCHITECTURE.md) | Pipeline, folder layout, state model |
| [`DOCS/RULES.md`](DOCS/RULES.md) | Binding engineering rules and the AI boundaries |
| [`DOCS/DESIGN.md`](DOCS/DESIGN.md) | Palette, type scale, the A6 card |
| [`DOCS/PHASES.md`](DOCS/PHASES.md) | Roadmap with exit criteria |
| [`PLAN.md`](PLAN.md) | 4-day schedule, model benchmark, risk register |
| [`.agents/MEMORY.md`](.agents/MEMORY.md) | Running log — decisions, bugs, lessons |

## Licence

MIT. See [`LICENSE`](LICENSE).