"""Sloth Drawer — read the manuals you already own, print one card per device.

The package is deliberately small and layered. The deterministic core
(``extract.verify``, ``corpus.prefilter``) is pure text processing with no
project dependencies beyond :mod:`sloth_drawer.errors`; everything else builds
on top of it.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
