"""The extraction call: one fact, one call, one flat schema.

The rules this module enforces, because they are the ones that make the card
trustworthy:

*   **One fact per call.** Never an array of facts (PLAN.md 3.1). ``phi4-mini``
    answers an array schema with ``{"intervals": []}`` — valid JSON, nothing
    in it — so the extractor never asks for one.
*   **One chunk per call.** The model never sees more than a single excerpt
    (C5).
*   **Deterministic.** ``temperature 0`` and a fixed seed, set in the client.
*   **A bad answer is repaired once, then rejected.** The repair re-asks the
    same question with the validation error appended; it does not re-phrase the
    question to shop for a nicer answer (RULES.md 4.3).

What the model is *not* allowed to do here is decide whether the answer is
true. That is :mod:`sloth_drawer.extract.verify`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sloth_drawer.errors import ModelOutputError, ModelSchemaError
from sloth_drawer.extract.ollama import DEFAULT_TIMEOUT, Reply, generate
from sloth_drawer.extract.prompts import EXTRACT_SCHEMA, build_extract_prompt


@dataclass(frozen=True)
class Extraction:
    """One model answer about one excerpt."""

    output: dict
    replies: tuple[Reply, ...]

    @property
    def elapsed(self) -> float:
        return sum(reply.elapsed for reply in self.replies)

    @property
    def tokens(self) -> int:
        return sum(reply.total_tokens for reply in self.replies)

    @property
    def retries(self) -> int:
        return sum(reply.retries for reply in self.replies)


def _parse(text: str) -> dict:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ModelSchemaError(f"The model did not answer with JSON: {exc.msg}.") from exc
    if not isinstance(payload, dict):
        raise ModelSchemaError("The model answered with JSON that was not an object.")
    return payload


def _check_shape(payload: dict) -> dict:
    """Reject the known-empty answer instead of accepting it silently.

    ``phi4-mini`` under an array schema returns ``{"intervals": []}`` — the
    shape is valid and the content is empty. The extractor never uses an array
    schema, but a model may still answer with one, and accepting an empty list
    as "no intervals found" would hide a failure (RULES.md 2.3).
    """
    intervals = payload.get("intervals")
    if isinstance(intervals, list) and not intervals:
        raise ModelOutputError("The model returned an empty interval list.")
    return payload


def extract(
    excerpt: str,
    *,
    model: str,
    host: str,
    timeout: float = DEFAULT_TIMEOUT,
    section: str | None = None,
    keep_alive: str | int | None = None,
) -> Extraction:
    """Ask the model for one maintenance interval from one excerpt."""
    prompt = build_extract_prompt(excerpt, section)
    replies: list[Reply] = []

    reply = generate(
        model,
        prompt,
        EXTRACT_SCHEMA,
        host=host,
        timeout=timeout,
        keep_alive=keep_alive,
    )
    replies.append(reply)

    try:
        payload = _check_shape(_parse(reply.text))
    except (ModelSchemaError, ModelOutputError) as first:
        # One repair attempt: the same question, with the validation error
        # appended. Not a re-phrasing — a retry with better information.
        repair = generate(
            model,
            f"{prompt}\n\nYour previous answer could not be used: {first}\n"
            "Answer again with a single JSON object.",
            EXTRACT_SCHEMA,
            host=host,
            timeout=timeout,
            keep_alive=keep_alive,
        )
        replies.append(repair)
        payload = _check_shape(_parse(repair.text))

    return Extraction(output=payload, replies=tuple(replies))
