"""The design tokens, shared by the HTML card and the terminal card.

Everything here comes from ``DESIGN.md``: the palette, the type scale, the
verdict glyphs. Both renderers read from this one module so a card and a
terminal card can never drift apart, and so a change to the palette is a change
in one place.

Three rules from the design that are enforced here rather than hoped for:

*   **No network.** There is no ``@font-face`` and no URL in this module. The
    card is a single file with system font stacks, so it renders on a machine
    that has been offline for a month.
*   **No state is carried by colour alone.** Every verdict has a glyph and a
    word; the colour is the third signal, not the first.
*   **Numerals are tabular.** A column of dates that does not line up is the
    fastest way to make a maintenance schedule unusable.
"""

from __future__ import annotations

import os
from typing import TextIO

#: Surfaces and ink (DESIGN.md 2.1).
SURFACES: dict[str, str] = {
    "canvas": "#F2EFE9",
    "surface": "#FBFAF7",
    "surface_sunk": "#F5F2EC",
    "ink": "#1F1B18",
    "ink_muted": "#6B6259",
    "ink_faint": "#746B62",
    "rule": "#E0D9CE",
    "rule_strong": "#C9C0B2",
}

#: Accent and semantic states (DESIGN.md 2.2). Each has a foreground and a tint.
STATES: dict[str, tuple[str, str]] = {
    "accent": ("#4F6F52", "#E7EDE6"),
    "PASS": ("#3F6B48", "#E7EFE7"),
    "REPAIR": ("#8A5F1F", "#F6EEDD"),
    "REJECT": ("#9B3B30", "#F7E9E6"),
    "source": ("#3D5A73", "#E8EEF3"),
}

#: Verdict glyph, label and the meaning to the reader (DESIGN.md 2.4).
VERDICTS: dict[str, tuple[str, str, str]] = {
    "PASS": ("✓", "VERIFIED", "The code found this sentence in the cited page and re-derived it"),
    "REPAIR": ("↺", "CORRECTED", "The model's number was wrong; the source's number is printed"),
    "REJECT": ("⊘", "NOT FOUND", "No verifiable interval — nothing is printed as a fact"),
    "SKIP": ("⊘", "NOT FOUND", "No verifiable interval — nothing is printed as a fact"),
}

#: ASCII replacements for ``--ascii`` terminals (DESIGN.md 5.3).
ASCII_VERDICTS: dict[str, str] = {
    "PASS": "[x]",
    "REPAIR": "[!]",
    "REJECT": "[-]",
    "SKIP": "[-]",
}

#: Characters that have an ASCII spelling. ``--ascii`` is a full alternative,
#: not a degradation: the card must read in a log file or a CI transcript that
#: has never heard of Unicode.
_ASCII_TRANSLATION = str.maketrans(
    {
        "·": "-",
        "…": "...",
        "—": "-",
        "–": "-",
        "“": '"',
        "”": '"',
        "✓": "[x]",
        "↺": "[!]",
        "⊘": "[-]",
        "™": "(TM)",
        "®": "(R)",
        "©": "(c)",
        "≈": "~",
        "≤": "<=",
        "≥": ">=",
    }
)

#: System font stacks only. A card must not download a typeface.
FONTS: dict[str, str] = {
    "display": 'ui-serif, Georgia, "Iowan Old Style", "Palatino Linotype", Palatino, '
    '"Times New Roman", serif',
    "body": 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    "mono": (
        'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace'
    ),
}

#: Type scale (DESIGN.md 4): token -> (size in pt, line-height, weight, tracking).
TYPE: dict[str, tuple[float, float, int, str]] = {
    "eyebrow": (7.5, 1.3, 600, "0.14em"),
    "title": (15.0, 1.25, 600, "-0.01em"),
    "subtitle": (8.5, 1.4, 400, "0"),
    "hero": (30.0, 1.0, 700, "-0.02em"),
    "hero_unit": (12.0, 1.0, 500, "0.02em"),
    "hero_label": (7.5, 1.3, 600, "0.14em"),
    "task": (9.5, 1.35, 500, "0"),
    "due": (11.0, 1.3, 600, "0"),
    "evidence": (8.5, 1.5, 400, "0"),
    "citation": (7.5, 1.3, 500, "0.06em"),
    "chip": (7.0, 1.2, 700, "0.08em"),
    "body": (9.0, 1.5, 400, "0"),
    "mono": (8.5, 1.45, 400, "0"),
}

#: The card's physical size (DESIGN.md 5). A6, one device per card.
CARD_WIDTH_MM = 81
CARD_MIN_HEIGHT_MM = 124
PAGE_MARGIN_MM = 12

#: Terminal palette, 256-colour (DESIGN.md 2.3).
TERMINAL_COLORS: dict[str, int] = {
    "accent": 108,
    "PASS": 71,
    "REPAIR": 172,
    "REJECT": 167,
    "SKIP": 167,
    "source": 110,
    "ink_faint": 245,
}

RESET = "\x1b[0m"
BOLD = "\x1b[1m"

#: The terminal card is exactly this wide, box drawing included.
TERMINAL_WIDTH = 80


def to_ascii(text: str) -> str:
    """Spell every character that has an ASCII form the ASCII way.

    A manual is full of ``™``, ``·`` and en dashes, and the model copies them
    into the task names. Anything left over is replaced rather than allowed to
    reach a terminal that cannot render it.
    """
    return text.translate(_ASCII_TRANSLATION).encode("ascii", "replace").decode("ascii")


def verdict_glyph(status: str, *, ascii_only: bool = False) -> str:
    """The glyph that carries a verdict's state without relying on colour."""
    if ascii_only:
        return ASCII_VERDICTS.get(status, "[-]")
    return VERDICTS.get(status, VERDICTS["REJECT"])[0]


def verdict_label(status: str) -> str:
    """The word beside the glyph. Never omitted."""
    return VERDICTS.get(status, VERDICTS["REJECT"])[1]


def verdict_chip(status: str, *, ascii_only: bool = False) -> str:
    """``✓ VERIFIED`` — glyph plus word, the two non-colour signals."""
    return f"{verdict_glyph(status, ascii_only=ascii_only)} {verdict_label(status)}"


def state_color(status: str) -> tuple[str, str]:
    """The (foreground, tint) pair for a verdict."""
    return STATES.get(status, STATES["REJECT"])


def supports_color(stream: TextIO, *, disabled: bool = False) -> bool:
    """Whether ANSI colour should be used on this stream.

    ``NO_COLOR=1`` and piping to a file both mean no colour: a card read in a
    log file should not be full of escape sequences (DESIGN.md 2.3).
    """
    if disabled or os.environ.get("NO_COLOR"):
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


def bold(text: str, enabled: bool) -> str:
    """The hero number: the only bold text on a terminal card (DESIGN.md 5.3)."""
    if not enabled:
        return text
    return f"{BOLD}{text}{RESET}"


def paint(text: str, role: str, enabled: bool, *, bold: bool = False) -> str:
    """Wrap text in a 256-colour code, or return it unchanged."""
    if not enabled:
        return text
    code = TERMINAL_COLORS.get(role)
    if code is None:
        return text
    prefix = f"{BOLD}\x1b[38;5;{code}m" if bold else f"\x1b[38;5;{code}m"
    return f"{prefix}{text}{RESET}"


def _declaration(token: str) -> str:
    size, line_height, weight, tracking = TYPE[token]
    return (
        f"font-size: {size:g}pt; line-height: {line_height:g}; "
        f"font-weight: {weight}; letter-spacing: {tracking};"
    )


def card_css() -> str:
    """The card's stylesheet. A single string, no imports, no URLs."""
    return f"""
@page {{ size: 105mm 148mm; margin: {PAGE_MARGIN_MM}mm; }}

:root {{
  --canvas: {SURFACES["canvas"]};
  --surface: {SURFACES["surface"]};
  --surface-sunk: {SURFACES["surface_sunk"]};
  --ink: {SURFACES["ink"]};
  --ink-muted: {SURFACES["ink_muted"]};
  --ink-faint: {SURFACES["ink_faint"]};
  --rule: {SURFACES["rule"]};
  --rule-strong: {SURFACES["rule_strong"]};
  --accent: {STATES["accent"][0]};
  --source: {STATES["source"][0]};
}}

* {{ box-sizing: border-box; }}

body {{
  margin: 0;
  padding: 12mm;
  background: var(--canvas);
  color: var(--ink);
  font-family: {FONTS["body"]};
  font-variant-numeric: tabular-nums;
}}

.card {{
  width: {CARD_WIDTH_MM}mm;
  min-height: {CARD_MIN_HEIGHT_MM}mm;
  background: #FFFFFF;
  border: 0.5pt solid var(--rule-strong);
  padding: 8mm;
  break-inside: avoid;
  page-break-inside: avoid;
}}

.eyebrow {{
  {_declaration("eyebrow")}
  text-transform: uppercase;
  color: var(--ink-muted);
}}

.title {{
  {_declaration("title")}
  font-family: {FONTS["display"]};
  margin: 1.5mm 0 0;
}}

.subtitle {{
  {_declaration("subtitle")}
  color: var(--ink-muted);
  margin: 0.8mm 0 0;
}}

.rule {{
  border: 0;
  border-top: 0.5pt solid var(--rule);
  margin: 5mm 0 4mm;
}}

.hero-label {{
  {_declaration("hero_label")}
  text-transform: uppercase;
  color: var(--ink-muted);
}}

.hero {{
  font-family: {FONTS["display"]};
  font-variant-numeric: tabular-nums;
  margin: 1mm 0 0;
}}

.hero-number {{
  {_declaration("hero")}
  color: var(--ink);
}}

.hero-unit {{
  {_declaration("hero_unit")}
  color: var(--ink-muted);
  margin-left: 2mm;
}}

.hero-none {{
  {_declaration("due")}
  color: var(--ink-faint);
}}

.task {{
  {_declaration("task")}
  margin: 4mm 0 0;
}}

.due {{
  {_declaration("due")}
  color: var(--accent);
  margin: 1mm 0 0;
}}

.due-none {{
  {_declaration("due")}
  color: var(--ink-faint);
  margin: 1mm 0 0;
}}

.chip {{
  {_declaration("chip")}
  display: inline-block;
  text-transform: uppercase;
  margin: 2mm 0 0;
  padding: 0.6mm 1.6mm;
  border: 0.5pt solid currentColor;
  border-radius: 2px;
}}

.chip-pass {{ color: {STATES["PASS"][0]}; background: {STATES["PASS"][1]}; }}
.chip-repair {{ color: {STATES["REPAIR"][0]}; background: {STATES["REPAIR"][1]}; }}
.chip-reject {{ color: {STATES["REJECT"][0]}; background: {STATES["REJECT"][1]}; }}

.evidence {{
  {_declaration("evidence")}
  font-style: italic;
  color: var(--ink-muted);
  background: var(--surface-sunk);
  border-left: 1.5pt solid var(--accent);
  padding: 2mm 0 2mm 3mm;
  margin: 5mm 0 0;
}}

.citation {{
  {_declaration("citation")}
  text-transform: uppercase;
  color: var(--source);
  margin: 2mm 0 0;
}}

.footnote {{
  {_declaration("chip")}
  color: {STATES["REPAIR"][0]};
  margin: 1.5mm 0 0;
}}

.tasks {{
  margin: 5mm 0 0;
  border-top: 0.5pt solid var(--rule);
  padding-top: 3mm;
}}

.tasks-title {{
  {_declaration("citation")}
  text-transform: uppercase;
  color: var(--ink-muted);
}}

.tasks ul {{ list-style: none; margin: 1.5mm 0 0; padding: 0; }}

.tasks li {{
  {_declaration("mono")}
  display: flex;
  justify-content: space-between;
  gap: 2mm;
  padding: 0.7mm 0;
  border-bottom: 0.5pt solid var(--rule);
}}

.tasks li:last-child {{ border-bottom: 0; }}

.tasks .row-task {{ color: var(--ink); }}
.tasks .row-due {{ color: var(--ink-muted); white-space: nowrap; }}

@media screen {{
  .card {{ background: var(--surface); }}
}}
"""
