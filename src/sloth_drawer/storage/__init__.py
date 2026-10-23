"""Local state: the SQLite database and the service log.

Everything the tool remembers between runs lives here, and none of it leaves
the machine. The cloud retrieval backend (``vector/``) is forbidden from
importing this package, which is what keeps a device name out of the index
(RULES.md 3.1a).
"""

from __future__ import annotations

from sloth_drawer.storage.db import (
    Device,
    IntervalRow,
    RunRecord,
    connect,
    intervals_for_device,
    load_devices,
    manual_index,
    open_db,
    record_run,
    upsert_device,
    upsert_interval,
)
from sloth_drawer.storage.service_log import (
    TaskSchedule,
    format_date,
    last_done,
    next_due,
    parse_date,
    record_done,
    schedule_for_device,
    sort_tasks,
)

__all__ = [
    "Device",
    "IntervalRow",
    "RunRecord",
    "TaskSchedule",
    "connect",
    "format_date",
    "intervals_for_device",
    "last_done",
    "load_devices",
    "manual_index",
    "next_due",
    "open_db",
    "parse_date",
    "record_done",
    "record_run",
    "schedule_for_device",
    "sort_tasks",
    "upsert_device",
    "upsert_interval",
]
