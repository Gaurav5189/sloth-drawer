"""The web surface's HTML, built from the same design tokens as the card.

The pages are deliberately plain server-rendered HTML with one inline
stylesheet and no JavaScript: the demo must survive a cold start on a free
tier, and a maintenance card is a *document*, not an app. Every colour,
surface and font stack comes from ``render.theme`` so the web pages and the
printable card can never drift apart (DESIGN.md 2).
"""

from __future__ import annotations

from datetime import date

from sloth_drawer.render.theme import FONTS, STATES, SURFACES, verdict_chip
from sloth_drawer.storage.db import Device
from sloth_drawer.storage.service_log import TaskSchedule

_TASK_ANCHOR = "task-"


def _css() -> str:
    """The inline stylesheet. Same palette and type stacks as the card."""
    return f"""
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
  --accent-tint: {STATES["accent"][1]};
  --repair: {STATES["REPAIR"][0]};
  --reject: {STATES["REJECT"][0]};
  --reject-tint: {STATES["REJECT"][1]};
  --source: {STATES["source"][0]};
}}

* {{ box-sizing: border-box; }}

body {{
  margin: 0;
  background: var(--canvas);
  color: var(--ink);
  font-family: {FONTS["body"]};
  font-variant-numeric: tabular-nums;
  line-height: 1.5;
}}

.wrap {{ max-width: 46rem; margin: 0 auto; padding: 1.5rem 1rem 3rem; }}

.crumbs {{
  font-size: 0.8125rem; letter-spacing: 0.02em; margin: 0 0 1rem;
}}
.crumbs a {{ color: var(--source); text-decoration: none; }}
.crumbs a:hover {{ text-decoration: underline; }}

.eyebrow {{
  font-size: 0.75rem; font-weight: 600; letter-spacing: 0.14em;
  text-transform: uppercase; color: var(--ink-muted); margin: 0 0 0.25rem;
}}

h1 {{
  font-family: {FONTS["display"]};
  font-size: 1.75rem; font-weight: 600; letter-spacing: -0.01em;
  margin: 0;
}}

.subtitle {{ color: var(--ink-muted); margin: 0.25rem 0 0; font-size: 0.9375rem; }}

.rule {{ border: 0; border-top: 1px solid var(--rule); margin: 1.25rem 0; }}

.device-list {{
  list-style: none; margin: 0; padding: 0;
  border: 1px solid var(--rule-strong);
  border-radius: 4px; background: var(--surface);
}}
.device-list li {{
  border-bottom: 1px solid var(--rule);
  padding: 0.75rem 1rem;
  display: flex; align-items: baseline; gap: 0.75rem; flex-wrap: wrap;
}}
.device-list li:last-child {{ border-bottom: 0; }}
.device-list a {{
  font-family: {FONTS["display"]}; font-size: 1.0625rem; font-weight: 600;
  color: var(--ink); text-decoration: none;
}}
.device-list a:hover {{ color: var(--source); }}
.device-list .meta {{ color: var(--ink-muted); font-size: 0.8125rem; flex: 1 1 12rem; }}
.due-tag {{
  font-size: 0.75rem; font-weight: 600; white-space: nowrap;
  color: var(--accent); background: var(--accent-tint);
  padding: 0.125rem 0.5rem; border-radius: 2px;
}}
.due-tag.overdue {{ color: var(--reject); background: var(--reject-tint); }}
.due-tag.none {{ color: var(--ink-faint); background: none; }}

.badge {{
  display: inline-block; font-size: 0.6875rem; font-weight: 700;
  letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--ink-faint); border: 1px solid var(--rule-strong);
  padding: 0.125rem 0.5rem; border-radius: 2px; white-space: nowrap;
}}

.tasks {{ list-style: none; margin: 0; padding: 0; }}
.task {{
  border: 1px solid var(--rule-strong); border-radius: 4px;
  background: var(--surface); padding: 1rem; margin: 0 0 0.75rem;
}}
.task .head {{ display: flex; gap: 0.5rem; align-items: baseline; flex-wrap: wrap; }}
.task .name {{ font-weight: 600; margin: 0; flex: 1 1 10rem; }}
.task .interval {{ color: var(--ink-muted); font-size: 0.8125rem; white-space: nowrap; }}
.task .evidence {{
  font-size: 0.875rem; font-style: italic; color: var(--ink-muted);
  background: var(--surface-sunk); border-left: 3px solid var(--accent);
  margin: 0.625rem 0 0; padding: 0.375rem 0 0.375rem 0.75rem;
}}
.task .due-row {{
  display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; margin-top: 0.625rem;
}}
.task .due-text {{ font-weight: 600; color: var(--accent); font-size: 0.9375rem; }}
.task .due-text.overdue {{ color: var(--reject); }}
.task .due-text.none {{ color: var(--ink-faint); font-weight: 400; }}
.task .disagree {{
  color: var(--repair); font-size: 0.6875rem;
  font-weight: 700; letter-spacing: 0.08em;
}}

form.mark-done {{ display: inline; }}
button {{
  font: inherit; font-size: 0.875rem; font-weight: 600;
  color: var(--accent); background: var(--accent-tint);
  border: 1px solid var(--accent); border-radius: 3px;
  padding: 0.25rem 0.75rem; cursor: pointer;
}}
button:hover {{ background: var(--accent); color: #FFFFFF; }}
button:not(:focus-visible) {{ outline: none; }}
button:focus-visible {{ outline: 2px solid var(--source); outline-offset: 2px; }}

.flash {{
  color: var(--accent); background: var(--accent-tint); border: 1px solid var(--accent);
  border-radius: 4px; padding: 0.5rem 1rem; margin: 0 0 1rem; font-size: 0.9375rem;
}}

.card-link {{ font-size: 0.875rem; color: var(--source); }}
.empty {{ color: var(--ink-faint); margin: 1rem 0; }}
.error main {{ max-width: 46rem; margin: 0 auto; padding: 1.5rem 1rem; }}
.error .code {{
  font-family: {FONTS["mono"]}; color: var(--ink-faint); font-size: 0.8125rem;
}}
.error .detail {{ background: var(--surface-sunk); padding: 0.75rem 1rem; border-radius: 4px; }}
footer {{ color: var(--ink-faint); font-size: 0.8125rem; margin-top: 2rem; }}
    """


def shell(title: str, body: str) -> str:
    """One HTML document, tokens included, no network requests."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{_css()}</style>
</head>
<body>
{body}
</body>
</html>
"""


def _due_tag(due: date | None) -> tuple[str, str]:
    """(text, css class) for one due date. State is never colour-only."""
    if due is None:
        return "no due date", "none"
    if due < date.today():
        return f"OVERDUE since {due.strftime('%d %b %Y')}", "overdue"
    return f"DUE {due.strftime('%d %b %Y')}", ""


def _soonest(tasks: list[TaskSchedule]) -> date | None:
    """The earliest next-due across a device's accepted tasks."""
    dues = [task.next_due for task in tasks if task.accepted]
    dated = [due for due in dues if due is not None]
    return min(dated) if dated else None


def device_list_page(
    entries: list[tuple[Device, list[TaskSchedule], bool]],
) -> str:
    """The front page: every device in the registry, scanned ones linked."""
    items = []
    for device, tasks, scanned in entries:
        if scanned:
            text, klass = _due_tag(_soonest(tasks))
            tag = f'<span class="due-tag {klass}">{text}</span>'
            count = len([task for task in tasks if task.accepted])
            meta = f"{count} task{'s' if count != 1 else ''} on the card"
            link = f'<a href="/device/{device.slug}">{device.name}</a>'
        else:
            tag = '<span class="badge">not scanned</span>'
            meta = "run <code>sloth-drawer scan</code> first"
            link = f"<strong>{device.name}</strong>"
        items.append(
            f"<li>{link}<span class=\"meta\">{device.subtitle} · {meta}</span>{tag}</li>"
        )
    listing = "<ul class=\"device-list\">" + "\n".join(items) + "</ul>" if items else ""
    body = f"""<main class="wrap">
<p class="eyebrow">Sloth Drawer</p>
<h1>The drawer</h1>
<p class="subtitle">One maintenance card per device, read from the manual you own.</p>
<hr class="rule">
{listing}
<footer>The card is the same HTML <code>sloth-drawer card</code> writes to out/cards/.</footer>
</main>"""
    return shell("Sloth Drawer — the drawer", body)


def device_page(device: Device, tasks: list[TaskSchedule], flash: str = "") -> str:
    """One device: the card's tasks, each with a Mark-done form.

    A rejected task shows as NOT FOUND on the card, so it offers no form —
    there is no verified interval to schedule against.
    """
    items = []
    ordered = sorted(tasks, key=lambda task: (not task.accepted, task.task.lower()))
    for task in ordered:
        if task.accepted:
            text, klass = _due_tag(task.next_due)
            last = (
                f'<span class="badge">last {task.last_done.strftime("%d %b %Y")}</span>'
                if task.last_done is not None
                else '<span class="badge">never logged</span>'
            )
            form = (
                f'<form class="mark-done" method="post" '
                f'action="/device/{device.slug}/done?interval_id={task.interval_id}">'
                f"<button type=\"submit\">Mark done</button></form>"
            )
            disagree = (
                f'<span class="disagree">{task.disagreement}</span>' if task.disagreement else ""
            )
            due_row = (
                f'<div class="due-row"><span class="due-text {klass}">'
                f"{text}</span>{last}{form}{disagree}</div>"
            )
        else:
            reason = task.reject_reason or "the manual states no verifiable interval"
            due_row = (
                '<div class="due-row"><span class="badge">not on the card</span>'
                f'<span class="interval">{reason}</span></div>'
            )
        evidence = (
            f'<blockquote class="evidence">{task.evidence}</blockquote>' if task.evidence else ""
        )
        chips = verdict_chip(task.verdict)
        items.append(
            f'<li class="task" id="{_TASK_ANCHOR}{task.interval_id}">'
            f'<div class="head"><span class="badge">{chips}</span>'
            f'<p class="name">{task.task}</p><span class="interval">{task.display}</span></div>'
            f"{evidence}{due_row}</li>"
        )
    listing = '<ul class="tasks">' + "\n".join(items) + "</ul>" if items else ""
    notice = f'<p class="flash" role="status">{flash}</p>' if flash else ""
    body = f"""<main class="wrap">
<nav class="crumbs"><a href="/">&larr; All devices</a></nav>
<p class="eyebrow">{(device.category or "device").replace("_", " ").replace("-", " ")}</p>
<h1>{device.name}</h1>
<p class="subtitle">{device.subtitle}</p>
<hr class="rule">
{notice}
<p><a class="card-link" href="/device/{device.slug}/card">Open the printable card &rarr;</a></p>
{listing}
</main>"""
    return shell(f"{device.name} — Sloth Drawer", body)


def error_page(code: int, title: str, detail: str) -> str:
    """Every handled failure lands here: a word to the user, not an imprimis."""
    body = f"""<main class="wrap">
<p class="code">HTTP {code}</p>
<h1>{title}</h1>
<p class="detail">{detail}</p>
<p><a class="card-link" href="/">&larr; Back to the drawer</a></p>
</main>"""
    return shell(f"{title} — Sloth Drawer", body)
