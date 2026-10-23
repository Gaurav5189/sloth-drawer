"""The A6 print card.

The card is the product. It gets taped to a device, so it has to survive a
kitchen and a printer: white paper, hairlines, one number treated as the hero,
and the manufacturer's own sentence printed underneath so a reader can check it
in ten seconds (DESIGN.md 5).

The output is a **single HTML file** — no scripts, no images, no web fonts, no
CDN. It opens in any browser and prints from there, on a machine that has never
been online.
"""

from __future__ import annotations

import html
import re

import sloth_drawer.render.theme as theme
from sloth_drawer.storage.db import Device
from sloth_drawer.storage.service_log import TaskSchedule, format_date, sort_tasks

#: Verbs a hero label can be built from. Anything else falls back to REPLACE.
_HERO_VERBS = ("replace", "clean", "wash", "check", "inspect", "service", "descale", "rinse")

#: The hero label when a task names no recognisable verb.
DEFAULT_HERO_LABEL = "REPLACE EVERY"


def hero_label(task: str) -> str:
    """``Pre-Carbon filter replacement`` -> ``REPLACE EVERY``.

    The label above the number comes from the task's own verb, so a cleaning
    interval is not printed as a replacement one. The verb is matched on its
    stem, because a manual writes "cleaning" and "replacement", not "clean".
    """
    words = re.findall(r"[a-z]+", task.lower())
    for verb in _HERO_VERBS:
        if any(word.startswith(verb) for word in words):
            return f"{verb.upper()} EVERY"
    return DEFAULT_HERO_LABEL


def split_display(display: str) -> tuple[str, str]:
    """``2 weeks`` -> ``("2", "weeks")``. The number and its unit are set apart."""
    number, _, unit = display.rpartition(" ")
    if not number:
        return display, ""
    return number, unit


def citation(device: Device, task: TaskSchedule) -> str:
    """``MANUAL p.12 · 4.2 FILTER MAINTENANCE``.

    A citation without a page is not a citation, so the manual's filename is
    only used when the page is genuinely unknown.
    """
    if task.page is not None:
        parts = [f"MANUAL p.{task.page}"]
    else:
        parts = [f"MANUAL {device.manual_path or device.slug}"]
    if task.section:
        parts.append(task.section.upper())
    return " · ".join(parts)


def _chip(status: str) -> str:
    css = {"PASS": "chip-pass", "REPAIR": "chip-repair"}.get(status, "chip-reject")
    label = theme.verdict_label(status)
    glyph = theme.verdict_glyph(status)
    return (
        f'<p class="chip {css}"><span aria-hidden="true">{html.escape(glyph)}</span> '
        f"{html.escape(label)}</p>"
    )


def _due_line(task: TaskSchedule) -> str:
    if task.next_due is None:
        return '<p class="due-none">NEXT DUE &nbsp;— no service recorded</p>'
    return f'<p class="due">Next due &nbsp;{html.escape(format_date(task.next_due))}</p>'


def _hero(task: TaskSchedule) -> str:
    number, unit = split_display(task.display)
    unit_html = f'<span class="hero-unit">{html.escape(unit)}</span>' if unit else ""
    return (
        f'<p class="hero-label">{html.escape(hero_label(task.task))}</p>'
        f'<p class="hero"><span class="hero-number">{html.escape(number)}</span>{unit_html}</p>'
        f'<p class="task">{html.escape(task.task or "Maintenance task")}</p>'
        f"{_due_line(task)}"
        f"{_chip(task.verdict)}"
    )


def _evidence(task: TaskSchedule) -> str:
    """The evidence block, the citation, and the REPAIR footnote.

    No quote, no number: an interval without a verbatim source sentence is not
    printed on a card (DESIGN.md 5.1).
    """
    if not task.evidence:
        return ""
    block = f'<blockquote class="evidence">"{html.escape(task.evidence)}"</blockquote>'
    footnote = ""
    if task.disagreement:
        footnote = f'<p class="footnote">{html.escape(task.disagreement)}</p>'
    return block + footnote


def _not_found(tasks: list[TaskSchedule], device: Device) -> str:
    """The card a device gets when its manual states no verifiable interval.

    A blank card is a bug, so the card says what it looked at (DESIGN.md 5.1).
    """
    pages = sorted({task.page for task in tasks if task.page is not None})
    if pages:
        searched = "Searched pages " + ", ".join(str(page) for page in pages)
    else:
        searched = "No candidate page in this manual stated an interval"
    return (
        '<p class="hero-label">MAINTENANCE INTERVAL</p>'
        '<p class="hero-none">INTERVAL NOT FOUND</p>'
        f'<p class="task">{html.escape(searched)}.</p>'
        f'<p class="citation">MANUAL {html.escape(device.manual_path or device.slug)}</p>'
    )


def _other_tasks(tasks: list[TaskSchedule]) -> str:
    """The compact list below the hero. The card never becomes a wall of numbers."""
    if not tasks:
        return ""
    rows: list[str] = []
    for task in tasks:
        due = format_date(task.next_due) if task.next_due else "no service recorded"
        chip = theme.verdict_chip(task.verdict)
        rows.append(
            "<li>"
            f'<span class="row-task">{html.escape(task.task or "untitled")}</span>'
            f'<span class="row-due">{html.escape(due)} · {html.escape(chip)}</span>'
            "</li>"
        )
    return (
        '<section class="tasks">'
        '<p class="tasks-title">Other intervals on this device</p>'
        f"<ul>{''.join(rows)}</ul>"
        "</section>"
    )


def render_card(
    device: Device,
    tasks: list[TaskSchedule],
) -> str:
    """Render one device's A6 card as a standalone HTML document."""
    ordered = sort_tasks(tasks)
    accepted = [task for task in ordered if task.accepted]
    rejected = [task for task in ordered if not task.accepted]

    if accepted:
        hero = _hero(accepted[0])
        evidence = _evidence(accepted[0])
        citation_html = f'<p class="citation">{html.escape(citation(device, accepted[0]))}</p>'
        rest = accepted[1:] + rejected
    else:
        hero = _not_found(rejected, device)
        evidence = ""
        citation_html = ""
        rest = []

    eyebrow = (device.category or "device").replace("-", " ").replace("_", " ")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(device.name)} — maintenance card</title>
<style>{theme.card_css()}</style>
</head>
<body>
<main class="card">
  <p class="eyebrow">{html.escape(eyebrow)}</p>
  <h1 class="title">{html.escape(device.name)}</h1>
  <p class="subtitle">{html.escape(device.subtitle)}</p>
  <hr class="rule">
  {hero}
  {evidence}
  {citation_html}
  {_other_tasks(rest)}
</main>
</body>
</html>
"""


def card_filename(device: Device) -> str:
    """The file a device's card is written to."""
    return f"{device.slug}.html"
