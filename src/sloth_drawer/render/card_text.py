"""The 80-column terminal card.

The same artifact as the HTML card, in the place the tool actually runs. Two
constraints shape it (DESIGN.md 5.3):

*   **Exactly 80 columns.** A card that reflows is not a card.
*   **``--ascii`` is a full alternative, not a degradation.** Box drawing becomes
    ``+-|`` and the verdict glyphs become ``[x]``/``[!]``/``[-]``, so the card
    reads correctly in a terminal, a log file, or a CI transcript that has never
    heard of Unicode.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import sloth_drawer.render.theme as theme
from sloth_drawer.render.card_html import DEFAULT_HERO_LABEL, citation, hero_label, split_display
from sloth_drawer.storage.db import Device
from sloth_drawer.storage.service_log import TaskSchedule, format_date, sort_tasks

#: The card is exactly this wide, borders included.
WIDTH = theme.TERMINAL_WIDTH

#: The content area between the outer borders.
INNER = WIDTH - 2

#: The evidence box sits inside the content area with one space on each side.
NESTED = INNER - 2

#: The evidence text wraps at the nested box's inner width.
NESTED_TEXT = NESTED - 4

#: ANSI colour sequences. They occupy no columns, so they are stripped before a
#: line is measured — otherwise a coloured card would be a different width from
#: a plain one.
ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


def _visible_len(text: str) -> int:
    return len(ANSI_PATTERN.sub("", text))


@dataclass(frozen=True)
class _Frame:
    """The box-drawing characters, swapped wholesale for ``--ascii``."""

    tl: str
    tr: str
    bl: str
    br: str
    h: str
    v: str
    lm: str
    rm: str


UNICODE_FRAME = _Frame(tl="┌", tr="┐", bl="└", br="┘", h="─", v="│", lm="├", rm="┤")
ASCII_FRAME = _Frame(tl="+", tr="+", bl="+", br="+", h="-", v="|", lm="+", rm="+")


def _truncate(text: str, width: int, *, ascii_only: bool = False) -> str:
    """Cut to width with an ellipsis. The terminal card truncates, the HTML wraps."""
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    marker = "..." if ascii_only else "…"
    return text[: width - len(marker)] + marker


def _wrap(text: str, width: int) -> list[str]:
    """Greedy word wrap. A word longer than the line is cut, never overflowed."""
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    for word in words:
        while len(word) > width:
            if current:
                lines.append(current)
                current = ""
            lines.append(word[:width])
            word = word[width:]
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= width:
            current = f"{current} {word}"
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


class _Renderer:
    """Accumulates the card's lines, then joins them."""

    def __init__(self, *, color: bool, ascii_only: bool) -> None:
        self.color = color
        self.ascii_only = ascii_only
        self.frame = ASCII_FRAME if ascii_only else UNICODE_FRAME
        self.lines: list[str] = []

    def paint(self, text: str, role: str, *, bold: bool = False) -> str:
        return theme.paint(text, role, self.color, bold=bold)

    def t(self, text: str) -> str:
        """Spell the text the ASCII way when ``--ascii`` is on.

        Applied at the source, before any width is computed: ``™`` becomes
        ``(TM)`` and a line measured before that would overflow its box.
        """
        return theme.to_ascii(text) if self.ascii_only else text

    def row(self, content: str = "") -> None:
        """One line of the content area, padded or cut to ``INNER``.

        Widths are measured with the colour codes removed: an escape sequence
        is not a column, and a coloured card must line up exactly like a plain
        one.
        """
        content = self.t(content)
        visible = _visible_len(content)
        if visible > INNER and "\x1b" not in content:
            content = _truncate(content, INNER, ascii_only=self.ascii_only)
            visible = len(content)
        padding = " " * max(0, INNER - visible)
        self.lines.append(f"{self.frame.v}{content}{padding}{self.frame.v}")

    def rule(self) -> None:
        """The hairline under the header, using the join characters."""
        self.lines.append(f"{self.frame.lm}{self.frame.h * INNER}{self.frame.rm}")

    def top(self) -> None:
        self.lines.append(f"{self.frame.tl}{self.frame.h * INNER}{self.frame.tr}")

    def bottom(self) -> None:
        self.lines.append(f"{self.frame.bl}{self.frame.h * INNER}{self.frame.br}")

    def nested(self, text_lines: list[str]) -> None:
        """The evidence box: a box inside the content area, one space in."""
        top = f"{self.frame.tl}{self.frame.h * (NESTED - 2)}{self.frame.tr}"
        bottom = f"{self.frame.bl}{self.frame.h * (NESTED - 2)}{self.frame.br}"
        self.row(f" {top} ")
        for line in text_lines:
            inner = self.t(line).ljust(NESTED_TEXT)[:NESTED_TEXT]
            self.row(f" {self.frame.v} {inner} {self.frame.v} ")
        self.row(f" {bottom} ")

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


def _header(renderer: _Renderer, device: Device) -> None:
    eyebrow = renderer.t((device.category or "device").replace("-", " ").replace("_", " ").upper())
    name = renderer.t(device.name)
    available = INNER - 2
    if len(eyebrow) < available:
        name = _truncate(name, available - len(eyebrow) - 1, ascii_only=renderer.ascii_only)
        gap = " " * (available - len(name) - len(eyebrow))
        renderer.row(f" {name}{gap}{eyebrow}")
    else:
        renderer.row(f" {_truncate(name, available, ascii_only=renderer.ascii_only)}")
    renderer.row(f" {renderer.t(device.subtitle)}")


def _hero(renderer: _Renderer, task: TaskSchedule) -> None:
    number, unit = split_display(task.display)
    renderer.row()
    renderer.row(f" {renderer.t(hero_label(task.task))}")
    renderer.row(" " + theme.bold(renderer.t(f"{number} {unit}".strip()), renderer.color))
    renderer.row()
    renderer.row(f" {renderer.t(task.task or 'Maintenance task')}")
    if task.next_due is None:
        renderer.row(" " + renderer.paint("Next due  — no service recorded", "ink_faint"))
    else:
        renderer.row(" " + renderer.paint(f"Next due  {format_date(task.next_due)}", "accent"))
    chip = theme.verdict_chip(task.verdict, ascii_only=renderer.ascii_only)
    renderer.row(" " + renderer.paint(chip, task.verdict))


def _evidence(renderer: _Renderer, task: TaskSchedule) -> None:
    if not task.evidence:
        return
    # Translated before wrapping, so an ASCII expansion cannot overflow the box.
    wrapped = _wrap(renderer.t(f'"{task.evidence}"'), NESTED_TEXT)
    renderer.row()
    renderer.nested(wrapped)
    if task.disagreement:
        renderer.row(" " + renderer.paint(task.disagreement, "REPAIR"))


def _not_found(renderer: _Renderer, device: Device, tasks: list[TaskSchedule]) -> None:
    pages = sorted({task.page for task in tasks if task.page is not None})
    if pages:
        searched = "Searched pages " + ", ".join(str(page) for page in pages)
    else:
        searched = "No candidate page in this manual stated an interval"
    renderer.row()
    renderer.row(" MAINTENANCE INTERVAL")
    renderer.row(" " + renderer.paint("INTERVAL NOT FOUND", "ink_faint", bold=True))
    renderer.row()
    for line in _wrap(renderer.t(f"{searched}."), INNER - 2):
        renderer.row(f" {line}")
    renderer.row(" " + renderer.paint(f"MANUAL {device.manual_path or device.slug}", "source"))


def _other_tasks(renderer: _Renderer, tasks: list[TaskSchedule]) -> None:
    if not tasks:
        return
    renderer.row()
    renderer.row(" " + renderer.paint("OTHER INTERVALS", "ink_faint"))
    for task in tasks:
        due = format_date(task.next_due) if task.next_due else "no service recorded"
        chip = theme.verdict_chip(task.verdict, ascii_only=renderer.ascii_only)
        tail = renderer.t(f"{due} · {chip}")
        room = INNER - 5 - _visible_len(tail) - 1
        label = _truncate(
            renderer.t(task.task or "untitled"), max(8, room), ascii_only=renderer.ascii_only
        )
        gap = " " * max(1, INNER - 4 - _visible_len(label) - _visible_len(tail))
        renderer.row(f"   {label}{gap}{tail}")


def render_card(
    device: Device,
    tasks: list[TaskSchedule],
    *,
    color: bool = True,
    ascii_only: bool = False,
) -> str:
    """Render one device's card for an 80-column terminal."""
    renderer = _Renderer(color=color, ascii_only=ascii_only)
    ordered = sort_tasks(tasks)
    accepted = [task for task in ordered if task.accepted]
    rejected = [task for task in ordered if not task.accepted]

    renderer.top()
    _header(renderer, device)
    renderer.rule()
    if accepted:
        hero = accepted[0]
        _hero(renderer, hero)
        _evidence(renderer, hero)
        renderer.row(" " + renderer.paint(citation(device, hero), "source"))
        _other_tasks(renderer, accepted[1:] + rejected)
    else:
        _not_found(renderer, device, rejected)
    renderer.bottom()
    return renderer.text()


__all__ = ["ASCII_FRAME", "UNICODE_FRAME", "WIDTH", "render_card", "DEFAULT_HERO_LABEL"]
