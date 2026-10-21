# DESIGN — Sloth Drawer

> Palette, type, and the card layout.
> The card is the product. It gets taped to a device. It has to survive a kitchen and a printer.

---

## 1. Theme

**"A quiet card on a fridge."**

Not a dashboard. Not a product. A **small printed object** that tells you one thing, tells you where that
thing came from, and gets out of the way. The aesthetic references a workshop label, a library card
catalogue, and a Japanese product manual: warm paper, hairlines, generous whitespace, one number
treated as the hero, and the source text quoted rather than paraphrased.

Three rules the whole design follows:

1. **The number is the hero.** The interval is the largest thing on the card. Everything else supports it.
2. **The evidence is visible.** The manufacturer's own sentence is printed, in italics, with a page
   number. The user must be able to check it in ten seconds.
3. **No network, ever.** No web fonts, no CDN, no analytics, no images fetched at runtime. A local-first
   tool that downloads a typeface from Google is a joke about itself. **This is a hard rule.**

## 2. Colour palette

Warm-neutral paper, desaturated moss accent, and three semantic states that must be distinguishable
without relying on colour alone (each state also carries a text label and a shape).

### 2.1 Surfaces & ink
| Token | Hex | Use | Contrast on card surface |
|---|---|---|---|
| `canvas` | `#F2EFE9` | Screen background, terminal header band | — |
| `surface` | `#FBFAF7` | Card surface | — |
| `surface-sunk` | `#F5F2EC` | Evidence block background, table zebra | — |
| `ink` | `#1F1B18` | Primary text, hero number | 16.2 : 1 |
| `ink-muted` | `#6B6259` | Supporting text, evidence quote | 5.7 : 1 |
| `ink-faint` | `#746B62` | Citations, page numbers, metadata | 5.0 : 1 |
| `rule` | `#E0D9CE` | Hairlines, table rules | decorative |
| `rule-strong` | `#C9C0B2` | Card border, table header rule | decorative |

### 2.2 Accent & semantic states
| Token | Hex | Use | Tint background | Contrast on surface |
|---|---|---|---|---|
| `accent` | `#4F6F52` | Moss — "verified", the next-due date, links | `#E7EDE6` | 5.4 : 1 |
| `pass` | `#3F6B48` | Verdict: PASS | `#E7EFE7` | 6.5 : 1 |
| `repair` | `#8A5F1F` | Verdict: REPAIR (code corrected the model) | `#F6EEDD` | 5.4 : 1 |
| `reject` | `#9B3B30` | Verdict: REJECT | `#F7E9E6` | 6.6 : 1 |
| `source` | `#3D5A73` | Source / manual citations, page numbers | `#E8EEF3` | 6.9 : 1 |

All text pairs meet **WCAG AA (4.5 : 1)** on their own surface and on their own tint. Body copy meets
AAA (7 : 1). No state is signalled by colour alone — every verdict carries a word and a glyph.

### 2.3 Terminal palette (256-colour, with a no-colour fallback)
| Role | ANSI 256 | Hex |
|---|---|---|
| `accent` | 108 | `#87AF87` |
| `pass` | 71 | `#5FAF5F` |
| `repair` | 172 | `#D78700` |
| `reject` | 167 | `#D75F5F` |
| `source` | 110 | `#87AFD7` |
| `ink-faint` | 245 | `#8A8A8A` |

`--no-color` and `NO_COLOR=1` both disable ANSI entirely. Piping to a file forces no-colour.

### 2.4 Verdict glyphs (shape, not colour, carries the signal)
| Verdict | Glyph | Label | Meaning to the reader |
|---|---|---|---|
| PASS | `✓` | `VERIFIED` | The code found this sentence in the cited page and re-derived the same interval |
| REPAIR | `↺` | `CORRECTED` | The code found the sentence but the model's number was wrong; the code's number is printed |
| REJECT | `⊘` | `NOT FOUND` | No verifiable interval — nothing is printed as a fact |

## 3. Fonts

**System stacks only. No web fonts, no `@font-face`, no download.** The card must render identically on
a machine that has been offline for a month.

| Role | Stack | Notes |
|---|---|---|
| Display / headings | `ui-serif, Georgia, "Iowan Old Style", "Palatino Linotype", Palatino, "Times New Roman", serif` | A warm bookish serif is available on every OS |
| Body / UI | `system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif` | |
| Mono / code / terminal | `ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace` | For the terminal card, the report table, and code in evidence |
| Numerals | `font-variant-numeric: tabular-nums` | Dates and intervals must align in columns. Always on the hero number |

**Rationale.** A serif for the device name makes the card feel like a printed object rather than a web
page. Tabular numerals are non-negotiable: a column of dates that do not line up is the fastest way to
make a maintenance schedule unusable.

## 4. Typography scale

Base unit 4px. All sizes in `pt` for print (the card is a print artifact) with `px` equivalents noted
for the screen rendering.

| Token | Size / line-height | Weight | Tracking | Use |
|---|---|---|---|---|
| `eyebrow` | 7.5pt / 1.3 | 600 | 0.14em | Category, uppercase: `AIR PURIFIER` |
| `title` | 15pt / 1.25 | 600 | -0.01em | Device name |
| `subtitle` | 8.5pt / 1.4 | 400 | 0 | Manufacturer · model |
| `hero` | 30pt / 1.0 | 700 | -0.02em | The interval number |
| `hero-unit` | 12pt / 1.0 | 500 | 0.02em | `months` beside the number |
| `hero-label` | 7.5pt / 1.3 | 600 | 0.14em | `REPLACE EVERY` above the number |
| `task` | 9.5pt / 1.35 | 500 | 0 | Task label |
| `due` | 11pt / 1.3 | 600 | 0 | Next-due date |
| `evidence` | 8.5pt / 1.5 | 400 italic | 0 | The quoted manufacturer sentence |
| `citation` | 7.5pt / 1.3 | 500 | 0.06em | `MANUAL p.12 · 4.2 FILTER MAINTENANCE` |
| `chip` | 7pt / 1.2 | 700 | 0.08em | Verdict chip |
| `body` | 9pt / 1.5 | 400 | 0 | Web UI paragraphs |
| `mono` | 8.5pt / 1.45 | 400 | 0 | Report tables, terminal card |

**Rules**

- Line length in evidence quotes is capped at **62 characters** (≈81mm at 8.5pt italic) — the card is
  narrow, so quotes are wrapped by the renderer, never truncated.
- Never set the hero number below 24pt. It is the point of the card.
- Uppercase is used only for `eyebrow`, `citation` and `chip` — never for sentences.
- The evidence quote is the only italic text on the card. One italic style per artifact.

## 5. The A6 card

**Format:** A6, 105 × 148 mm. **Margins:** 12 mm. **Content area:** 81 × 124 mm.
One device per card. Print two-up on A4 if you want, but the canonical unit is one device.

```
┌────────────────────────────────────────────┐  ← rule-strong border, 0.5pt
│                                            │
│  AIR PURIFIER                              │  eyebrow, 7.5pt, 0.14em
│  DuraMax 900 Series Air Purifier           │  title, 15pt, 600
│  DuraMax · DX-900P                        │  subtitle, 8.5pt, ink-muted
│                                            │
│  ──────────────────────────────────────    │  hairline, rule
│                                            │
│  REPLACE EVERY                             │  hero-label, 7.5pt, 600
│  2  months                                 │  hero, 30pt, 700, tabular-nums
│                                            │
│  Pre-Carbon filter replacement             │  task, 9.5pt
│  Next due  14 Nov 2026                     │  due, 11pt, 600, accent
│  ✓ VERIFIED                                │  chip, 7pt
│                                            │
│  ┌──────────────────────────────────────┐  │
│  │ "The Pre-Carbon filter (Part No.     │  │  evidence, 8.5pt italic
│  │  DX-CF14) must be replaced every     │  │  on surface-sunk, 1.5pt accent left rule
│  │  2 months."                          │  │
│  └──────────────────────────────────────┘  │
│  MANUAL p.12 · 4.2 FILTER MAINTENANCE      │  citation, 7.5pt, source
│                                            │
└────────────────────────────────────────────┘
```

### 5.1 Anatomy rules
- **One hero.** A device card shows exactly one interval as the hero — the soonest due. Every other
  interval for that device is listed below in a compact task list, with its own due date. If a device
  has many intervals, the card shows the hero plus a list; it does not become a wall of equal numbers.
- **Hero is the soonest due**, not the most important. Recency is what a sloth can act on.
- **Every task carries its own verdict chip.** A card can show a REJECT next to a PASS, honestly.
- **The evidence block is always present for a printed interval.** No quote, no number.
- **`REPAIR` adds one footnote line**, in `repair` colour: `MODEL SAID 3 · SOURCE SAYS 2`. The user sees
  the disagreement rather than a quietly patched number.
- **`never recorded` state:** if no service has ever been logged, the due line reads
  `NEXT DUE  — no service recorded` in `ink-faint`, and the card still prints the interval and the
  evidence. An unlogged device is a normal state, not an error.
- **`interval not found` card:** a device whose manual yielded nothing verifiable still gets a card,
  reading `INTERVAL NOT FOUND` with the citation section showing which pages were searched. A blank
  card is a bug.

### 5.2 Print CSS
```css
@page { size: 105mm 148mm; margin: 12mm; }
.card {
  width: 81mm; min-height: 124mm;
  background: #FFFFFF;            /* print: white. Warm paper is a screen affordance */
  border: 0.5pt solid #C9C0B2;
  padding: 8mm;
  break-inside: avoid;
  page-break-inside: avoid;
}
.evidence { border-left: 1.5pt solid #4F6F52; padding-left: 3mm; }
@media screen { .card { background: #FBFAF7; } }
```
Warm paper is screen-only. On paper you want white — it prints, it photocopies, and it scans.

### 5.3 Terminal card (80 columns)
```
┌──────────────────────────────────────────────────────────────────────────┐
│ DuraMax 900 Series Air Purifier                            AIR PURIFIER   │
│ DuraMax · DX-900P                                                       │
├──────────────────────────────────────────────────────────────────────────┤
│ REPLACE EVERY                                                            │
│ 2 months                                          ← 30pt equivalent: bold │
│                                                                          │
│ Pre-Carbon filter replacement                                           │
│ Next due  14 Nov 2026                                                    │
│ ✓ VERIFIED                                                              │
│                                                                          │
│ ┌────────────────────────────────────────────────────────────────────────┐│
│ │ "The Pre-Carbon filter (Part No. DX-CF14) must be replaced every     ││
│ │  2 months."                                                            ││
│ └────────────────────────────────────────────────────────────────────────┘│
│ MANUAL p.12 · 4.2 FILTER MAINTENANCE                                    │
└──────────────────────────────────────────────────────────────────────────┘
```
- Exactly 80 columns. `--ascii` swaps box-drawing for `+-|` and the glyphs for `[x]`, `[!]`, `[-]`.
- The bold hero is the only bold text in the card.

## 6. Component inventory

| Component | Where | Purpose |
|---|---|---|
| `Card` | `render/card_html.py` | The A6 artifact. One device. |
| `TerminalCard` | `render/card_text.py` | 80-col equivalent |
| `Hero` | shared | The interval number + unit + label |
| `TaskRow` | shared | Task label, due date, verdict chip |
| `EvidenceBlock` | shared | The quoted sentence on a sunken surface with a left rule |
| `Citation` | shared | `MANUAL p.12 · 4.2 FILTER MAINTENANCE` |
| `VerdictChip` | shared | `✓ VERIFIED` / `↺ CORRECTED` / `⊘ NOT FOUND` |
| `RepairFootnote` | shared | `MODEL SAID 3 · SOURCE SAYS 2` |
| `ReportTable` | `report/build.py` | The accuracy table — mono, tabular numerals, zebra rows |
| `DeviceCard` | web UI | Grid card listing a device and its due state |

## 7. Accessibility

- Every verdict is text + glyph + colour, never colour alone.
- Body text ≥ 4.5 : 1; the evidence quote and the citation meet AA; the hero number is 16: 1.
- The card is legible in pure black and white (the hairlines and the chip labels carry the structure).
- `--ascii` gives a non-unicode, non-colour terminal card.
- The HTML card is a single file with no scripts, no images, and a `lang` attribute — it opens in any
  browser and prints from there.
- Long device names truncate with an ellipsis **in the terminal card only**; the HTML card wraps.

## 8. Anti-patterns

- No gradients, no shadows, no rounded corners above 3px, no emoji in the printed card.
- No red/green pairing as the only signal.
- No more than one accent colour per card.
- No centred text except the hero.
- No more than ~120 words of content on a card. If it does not fit, the card is doing the wrong job.
- No web fonts. No CDN. No tracking. Not on the web UI either.
