"""Entry point for ``python -m sloth_drawer``."""

from __future__ import annotations

import sys

from sloth_drawer.cli import main

if __name__ == "__main__":
    sys.exit(main())
