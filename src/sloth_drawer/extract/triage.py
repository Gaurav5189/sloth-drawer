"""The triage call: a cheap yes/no gate in front of the expensive extractor.

The 291 MB model is not trusted to extract anything. It is asked one question
— "does this excerpt state an interval?" — and its answer only decides whether
the 806 MB model is worth waking up (RULES.md 1.4, PLAN.md 3.4).

A "no" is not a failure. It is a SKIP with a reason code.
"""

from __future__ import annotations

from dataclasses import dataclass

from sloth_drawer.errors import ModelSchemaError
from sloth_drawer.extract.ollama import DEFAULT_TIMEOUT, Reply, generate
from sloth_drawer.extract.prompts import TRIAGE_SCHEMA, build_triage_prompt


@dataclass(frozen=True)
class TriageResult:
    """What the triage model said, and what it cost."""

    has_interval: bool
    task: str
    section: str
    reply: Reply

    @property
    def tokens(self) -> int:
        return self.reply.total_tokens


def parse_payload(text: str) -> dict:
    """Parse a model answer into a JSON object.

    Raises :class:`ModelSchemaError` when the answer is not a JSON object. The
    caller decides whether to repair it (RULES.md 2.3).
    """
    import json

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ModelSchemaError(f"The model did not answer with JSON: {exc.msg}.") from exc
    if not isinstance(payload, dict):
        raise ModelSchemaError("The model answered with JSON that was not an object.")
    return payload


def triage(
    excerpt: str,
    *,
    model: str,
    host: str,
    timeout: float = DEFAULT_TIMEOUT,
    section: str | None = None,
    keep_alive: str | int | None = None,
) -> TriageResult:
    """Ask the small model whether this excerpt states an interval."""
    prompt = build_triage_prompt(excerpt, section)
    reply = generate(
        model,
        prompt,
        TRIAGE_SCHEMA,
        host=host,
        timeout=timeout,
        keep_alive=keep_alive,
    )
    payload = parse_payload(reply.text)
    return TriageResult(
        has_interval=bool(payload.get("has_interval")),
        task=str(payload.get("task") or "").strip(),
        section=str(payload.get("section") or "").strip(),
        reply=reply,
    )
