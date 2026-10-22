"""Two retrieval backends behind one interface.

``local`` is SQLite FTS5 with the trigram tokenizer and needs nothing.
``tiger`` is pgvector plus BM25 on Tiger Cloud. The pipeline never asks which
one it has.
"""

from __future__ import annotations
