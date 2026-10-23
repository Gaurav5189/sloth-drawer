"""The renderers: one card, two surfaces.

``theme`` holds the tokens, ``card_html`` produces the printable A6 artifact and
``card_text`` produces its 80-column twin. Both consume the same
:class:`~sloth_drawer.storage.service_log.TaskSchedule`, so a device cannot show
one date on paper and another in the terminal.
"""

from __future__ import annotations

from sloth_drawer.render.card_html import card_filename
from sloth_drawer.render.card_html import render_card as render_card_html
from sloth_drawer.render.card_text import render_card as render_card_text

__all__ = ["card_filename", "render_card_html", "render_card_text"]
