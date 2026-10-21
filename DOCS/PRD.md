# PRD — Sloth Drawer

**Version:** 1.0 · **Date:** 2026-10-22 · **Owner:** solo · **Status:** approved for build
**Target deadline:** 2026-10-26T06:59:00Z (Hacktoberfest DEV Challenge Week 3, "Slow and Steady")

---

## 1. Problem

Every physical device you own came with a maintenance instruction somewhere — usually one sentence in a
90-page PDF you can never find again. The instructions are specific ("replace the Pre-Carbon filter
every 2 months", "after 720 hours of continuous operation, whichever occurs first") and they are the
thing that keeps the device alive. Nobody reads them, so the device quietly degrades, breaks early, or
gets thrown out while still working.

Three separate failures compound:

1. **Discovery** — the manual is gone or was never downloaded.
2. **Retrieval** — even with the PDF, finding the one line about the filter means scrolling 40 pages.
3. **Scheduling** — nobody turns "every 2 months" into a date they will actually remember.

## 2. Target user

**Primary — "The Accumulator."**
Owns 10–40 consumer devices (air purifier, robot vacuum, coffee machine, dehumidifier, e-bike, lawn
mower). Has the manuals somewhere on a laptop, or can download them in ten minutes. Is not a
professional technician. Knows the device needs attention but not when, so it either gets ignored or
gets serviced at the wrong time. Comfortable with a terminal. Does not want a subscription.

**Secondary — "The Repair-Side Maintainer."**
A small repair shop or a hobbyist who services other people's equipment. Needs a printable, per-device
service card for the bench, and needs to trust that the interval on it came from the manufacturer's
document rather than from a guess. **Trust is the feature for this user** — a wrong interval causes a
misrepair and a liability.

**Explicitly not the target:** enterprise IT, anyone needing a fleet-wide CMMS integration, anyone
expecting medical, safety-critical or vehicle-fleet guidance.

## 3. Goals

| # | Goal | How it is measured |
|---|---|---|
| G1 | Turn a folder of manual PDFs into one maintenance card per device | Card per device with ≥1 verified interval, or an explicit "no interval found" |
| G2 | Every printed interval is traceable to a page the user can check | 100 % of intervals carry a verbatim-quoted sentence + page number |
| G3 | Never print an interval the source text does not support | 0 unverified intervals. Rejections are reported, not hidden |
| G4 | Run with no internet, on a plain laptop, at zero recurring cost | Verified with the network off; no API key anywhere in the code |
| G5 | Make the daily cost of ownership visible as a date | `next_due` computed in code for every task |
| G6 | Be swappable at the model layer | `--model` flag; ≥2 models benchmarked and documented |

## 4. Non-goals

- **Not** a chatbot over your manuals. The output is a card, not a conversation.
- **Not** a general document Q&A system.
- **Not** a purchase/price tracker, a warranty-claim filer, or a repair-appointment scheduler.
- **Not** a service that needs an account, a server, or a phone home.
- **Not** a PDF editor. Sloth Drawer reads; it never modifies your manuals.
- **Not** a replacement for the manufacturer's safety instructions. It quotes them; it does not interpret
  safety-critical procedures.

## 5. Features

Priority: **M** = must (needed for submission), **S** = should, **C** = could.

| ID | Feature | Pri | Description |
|---|---|---|---|
| F1 | Corpus ingest | M | Read a directory of manual PDFs with `pypdf`; per-page text + page numbers; detect and record image-only PDFs instead of crashing |
| F2 | Chunking | M | Split pages into chunks that retain page number and section heading; keep chunk offsets so any text can be re-located in the source |
| F3 | Deterministic pre-filter | M | Regex scoring for interval-shaped language; drops ~80 % of chunks at zero model cost |
| F4 | Model cascade | M | Optional 270M triage → 1B extractor; `--model` to swap the extractor |
| F5 | One-fact extraction | M | Flat JSON schema, one interval per call, Ollama `format` constrained decoding, temperature 0 |
| F6 | **The verifier** | M | Locate the model's quote in the source page, expand to the enclosing sentence, re-parse the interval, compare → `PASS` / `REPAIR` / `REJECT` |
| F7 | Fail-closed output | M | A rejected or repaired interval is still shown, but flagged with its reason. A chunk with no verifiable interval produces nothing |
| F8 | Device registry | M | A small TOML file: device name, manufacturer, model, manual filename, category |
| F9 | Service state | M | SQLite store of `last_done` per (device, task); `next_due = last_done + interval_months`; "never recorded" when unknown |
| F10 | Card renderer | M | One A6 print card per device: hero interval, task list, evidence quote, page cite, next-due date |
| F11 | Terminal card | M | 80-column text card for the terminal, same data |
| F12 | Batch runner | M | Process a whole corpus, one transaction per manual, resumable |
| F13 | Accuracy report | M | `report.json` + `report.md`: manuals scanned, intervals found, verified, rejected, repaired, seconds, tokens, cost |
| F14 | CLI | M | `scan`, `card`, `done`, `report`, `models` subcommands |
| F15 | Sentry tracing | S | Optional; one transaction per manual, a span per stage, with token counts. Off unless a DSN is set |
| F16 | Web UI | S | FastAPI page: browse devices, see cards, mark a task done. Core dependency, not an extra |
| F17 | Vector index | S | pgvector + `pg_textsearch` hybrid index on Tiger Cloud. Core dependency, not an extra |
| F21 | Dual retrieval backend | M | One `Retriever` interface, two implementations: local SQLite FTS5 (trigram, offline, zero-config) and Tiger Cloud hybrid (pgvector + BM25 + RRF). Both must yield the same card |
| F18 | Spend forecast | C | TabPFN over your own service history → what the next 12 months of maintenance will cost |
| F19 | Spend export | C | `.ics` calendar of upcoming service dates |
| F20 | Duplicate detection | C | Flag intervals restated across several manuals of the same device |

## 6. User stories

- *As the Accumulator, I drop 12 manual PDFs into a folder and run one command, and I get 12 printable
  cards telling me what each device needs and when — without reading a single manual.*
- *As the Accumulator, I mark "filter cleaned" on 3 March, and the card now says the next one is due in
  June. I never have to remember a date.*
- *As the Repair-Side Maintainer, I read the card's evidence line — the manufacturer's own sentence,
  with the page number — so I know the interval I am quoting came from the document, not from a guess.*
- *As the Accumulator, I unplug the router from the internet and the tool still works, because my
  manuals and my model are both on this laptop.*
- *As a sceptic, I run it with `--model phi4-mini` and see that it is slower but that the verifier
  catches the same number of mistakes. I trust the card because the *code* checked the model.*

## 7. Requirements

### 7.1 Functional
1. `scan` MUST process a directory of PDFs and produce per-device interval records.
2. Every record MUST carry: device, task, interval in months, the verbatim source sentence, the page
   number, the section heading, and a verification verdict.
3. The tool MUST NOT emit an interval whose source sentence cannot be located in the cited page.
4. `card` MUST render every device, including devices where nothing was verified (as an explicit
   "interval not found" card, never as a silently empty one).
5. `done` MUST record a service event and recompute `next_due` in code.
6. `report` MUST be reproducible from the run and MUST contain the rejection reasons.
7. The tool MUST work with the network disabled and with no credentials configured.
8. The retrieval backend MUST be selected by configuration only, never by a conditional in the pipeline.
9. The local backend MUST complete the whole pipeline with no network, no DSN and no configuration.
10. The Tiger Cloud backend MUST never receive anything beyond manual chunk text and its embedding:
    no device names, no serial numbers, no purchase dates, no service history.
11. Both backends MUST produce the same card for the same manual. A divergence is a bug in one of them.

### 7.2 Non-functional
| Attribute | Requirement |
|---|---|
| Privacy | Zero network calls by default. Ollama must resolve to a loopback address — enforced, not assumed. With the Tiger backend set, **only manual text and embeddings** cross the wire |
| Portability | A user who sets no environment variable gets a complete, correct product. The cloud backend is an enhancement, never a prerequisite |
| Cost | $0 per run. No API key, no account, no quota |
| Hardware | 4 CPU cores, 8 GB RAM, no GPU. Default model ≤ 1 GB |
| Throughput | ≤ 2 min per manual on the reference box; a 12-manual corpus completes in ≤ 30 min |
| Determinism | `temperature 0`, fixed seed, one model call per chunk |
| Offline UI | No web fonts, no CDN assets, no analytics in the rendered card |
| Accessibility | Card text meets 4.5:1 contrast; the terminal card degrades to plain ASCII on request |
| Provenance | Every model output that reaches a card is reproducible from the recorded prompt + model id |

## 8. Assumptions

| # | Assumption | If wrong |
|---|---|---|
| A1 | The user can obtain text-based manual PDFs for at least 8 devices | Fall back to a narrower demo (6 devices, one device class) and say so |
| A2 | "Every N months" is the dominant interval form | The verifier's re-parser already handles days/weeks/years; the report shows a per-unit breakdown |
| A3 | A user knows when they last serviced something, if they serviced it at all | `never recorded` state handles it; card shows the interval and says "no service recorded" |
| A4 | `gemma3:1b` is accurate enough on this task | Switch extractor to `phi4-mini` behind `--model`; both passed the test suite |
| A5 | Judges reward a narrow, physical, measured artifact | — (validated against the Week 1 winners) |

## 9. Success metrics

| Metric | Target |
|---|---|
| Intervals with a verified page citation | 100 % |
| Verified intervals correct on hand-check | ≥ 90 % of emitted intervals |
| Rejections correctly identified as rejections | 100 % (no false accepts) |
| Models benchmarked and compared in the write-up | ≥ 2 |
| Partner categories claimed | ≥ 4 |
| Manuals processed end-to-end | ≥ 8 |

## 10. Constraints

- Python 3.11+ (reference box: 3.14). Stdlib-first; third-party dependencies must be justified in `RULES.md`.
- Inference via a **local** Ollama server. No cloud model providers, in any code path, ever.
- The dependency set for the core path must install in under 60 seconds on the reference box.
- The whole thing must be runnable from a fresh clone with two commands and no configuration.
- Retrieval is a local SQLite FTS5 index by default, and a Tiger Cloud Postgres with pgvector and
  `pg_textsearch` when `SLOTH_DATABASE_URL` is set. No third retrieval service is permitted.

## 11. Out of scope for v1

Spend forecast, `.ics` export, duplicate detection, PDF output (HTML card only), multi-user, packaged
binaries, any retrieval backend other than the two above.

The web UI and the vector index are **in scope** — they are core dependencies — but they are the last
things to be built, because the card, the verifier and the report are the deliverable.

## 12. Open questions

- Should the card be A6 or a half-letter sheet? → A6 (tape to the device). Confirm in `DESIGN.md`.
- Does the reference corpus support a two-device-class demo? → Only if time allows after the report.
- Should `phi4-mini` be the default on machines with ≥ 6 GB free RAM? → Keep `gemma3:1b` default everywhere
  for a consistent benchmark; document the alternative.
