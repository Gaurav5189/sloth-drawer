"""The web surface: server-rendered pages over the same storage the CLI uses.

Import discipline (RULES.md 3.1a): this package may import only
``sloth_drawer.errors``, ``sloth_drawer.storage`` and
``sloth_drawer.render``. Configuration is passed in as plain paths — the
``config`` module stays out, so nothing here can reach the model settings,
the retrieval backends or the extractors.
"""
