# Sloth Drawer

> Offline agent that reads the manual PDFs you already downloaded and prints **one maintenance card
> per device** — the interval, the manufacturer's own sentence, the page number, and the next date it
> is due.

**Status: Phase 2 — the engine works, cards and report are next.** The corpus scan (`sloth-drawer scan data/manuals`) prints verified intervals with page citations; 63 candidates yield 22 PASS / 13 REPAIR / 7 REJECT / 21 SKIP in ~13 min.

## What it is

You own a handful of devices. Each came with a manual. When the thing starts blinking you cannot find
the manual, and nobody remembers the filter is due every 2 months.

Sloth Drawer reads the manual PDFs already on your disk, finds the maintenance intervals, and quotes
the page they came from. Everything runs on your machine, offline, for free.

## Design in one line

> **The model points, the code quotes, the code recomputes.**

A 1B open-weight model is only ever allowed to *point at a candidate sentence*. Code then locates
that sentence in the cited page as a verbatim substring, expands it to the enclosing sentence,
re-parses the interval from it, and compares its own number with the model's. The code's number
wins, and every disagreement is printed rather than hidden. A model failure can produce a *missing*
card; it can never produce a wrong date.

## Running it today

```bash
uv sync
ollama serve &
ollama pull gemma3:270m && ollama pull gemma3:1b && ollama pull nomic-embed-text
uv run sloth-drawer models
```

`uv sync` installs the Python dependencies; the Ollama server is only needed for
`sloth-drawer models` and `sloth-drawer scan`.

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
