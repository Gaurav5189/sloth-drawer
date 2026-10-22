"""The package that reads manuals.

``ingest`` turns PDFs into pages, ``chunk`` turns pages into chunks, and
``prefilter`` decides which of those chunks are worth a model call.
"""

from __future__ import annotations
