"""The extraction layer: the model points, the code quotes and recomputes.

``prompts`` holds every prompt and schema. ``triage`` is the cheap yes/no
gate, ``extractor`` asks for one fact per call, and ``verify`` is the part
that decides whether an answer is real.
"""

from __future__ import annotations
