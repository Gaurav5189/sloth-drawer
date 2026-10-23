"""The report: the accuracy table the post quotes.

``build`` turns a scan into ``report.json`` and ``report.md``. Nothing here
touches the model or the network — it is arithmetic over what the run recorded.
"""

from __future__ import annotations

from sloth_drawer.report.build import (
    DeviceRow,
    Report,
    SkippedRow,
    from_scan,
    load_report,
    write_report,
)

__all__ = [
    "DeviceRow",
    "Report",
    "SkippedRow",
    "from_scan",
    "load_report",
    "write_report",
]
