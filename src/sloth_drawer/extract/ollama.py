"""The local Ollama client.

One POST, one JSON document, no SDK. ``urllib`` is in the standard library, and
the whole point of the project is that the inference path has no dependencies
beyond the ones the standard library ships (RULES.md 1.1).

The request shape is fixed by RULES.md 1.4 and does not vary:

*   ``temperature: 0`` and a fixed ``seed`` — **required**, so a run is
    reproducible;
*   ``stream: false`` — the CLI prints one card, not a token stream;
*   ``format`` carries a JSON Schema — never the bare string ``"json"``,
    which loses the field names.
"""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from sloth_drawer.errors import (
    ConfigError,
    ModelTimeoutError,
    OllamaUnavailableError,
)

#: How long the model is given to answer one question.
DEFAULT_TIMEOUT = 120.0

#: The context window every request uses. Big enough for a chunk, small enough
#: that a 1B model on 8 GB does not swap.
NUM_CTX = 4096

#: The seed. Fixed so the same chunk produces the same answer twice.
SEED = 42

#: Backoff between retries, in seconds.
BACKOFF = (2.0, 4.0)

#: Ollama's own endpoints.
GENERATE_PATH = "/api/generate"
EMBED_PATH = "/api/embed"
TAGS_PATH = "/api/tags"


@dataclass(frozen=True)
class Reply:
    """One model answer, with the accounting the report needs."""

    text: str
    elapsed: float
    input_tokens: int
    output_tokens: int
    retries: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def post_json(host: str, path: str, payload: dict, timeout: float) -> tuple[dict, float]:
    """POST a JSON document to the local server and return the reply.

    Fails fast when the server is not there: if Ollama is not listening it will
    not start listening in two seconds either (RULES.md 2.3).
    """
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{host.rstrip('/')}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:200]
        except Exception:  # noqa: BLE001 - the error body is a nicety, not the point
            detail = ""
        if exc.code == 404 and "model" in detail.lower():
            raise ConfigError(
                f'Model "{payload.get("model", "?")}" is not pulled. '
                f"Run: ollama pull {payload.get('model', '?')}"
            ) from exc
        raise OllamaUnavailableError(
            f"Ollama at {host} replied with HTTP {exc.code} for {path}. {detail}".strip()
        ) from exc
    except TimeoutError as exc:
        raise ModelTimeoutError(f"Ollama did not answer within {timeout:g}s.") from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, (TimeoutError, socket.timeout)):
            raise ModelTimeoutError(f"Ollama did not answer within {timeout:g}s.") from exc
        raise OllamaUnavailableError(
            f'Cannot reach Ollama at {host}. Start it with "ollama serve".'
        ) from exc
    except OSError as exc:
        raise OllamaUnavailableError(
            f'Cannot reach Ollama at {host}. Start it with "ollama serve".'
        ) from exc

    elapsed = time.monotonic() - started
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ModelTimeoutError("Ollama replied with something that is not JSON.") from exc
    if not isinstance(decoded, dict):
        raise ModelTimeoutError("Ollama replied with an unexpected payload.")
    return decoded, elapsed


def generate(
    model: str,
    prompt: str,
    schema: dict,
    *,
    host: str,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = 2,
    keep_alive: str | int | None = None,
) -> Reply:
    """Ask the local model one question and return its answer.

    A timeout is retried with a backoff, then raised as
    :class:`ModelTimeoutError` — the caller records it as a rejected
    candidate and the batch continues. Every attempt's tokens are counted, so
    a retry can never hide its cost (RULES.md 2.3).
    """
    payload: dict = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": schema,
        "options": {"temperature": 0, "num_ctx": NUM_CTX, "seed": SEED},
    }
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive

    last_timeout: ModelTimeoutError | None = None
    for attempt in range(retries + 1):
        try:
            document, elapsed = post_json(host, GENERATE_PATH, payload, timeout)
        except ModelTimeoutError as exc:
            last_timeout = exc
            if attempt >= retries:
                break
            time.sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])
            continue
        return Reply(
            text=document.get("response", "") or "",
            elapsed=elapsed,
            input_tokens=int(document.get("prompt_eval_count", 0) or 0),
            output_tokens=int(document.get("eval_count", 0) or 0),
            retries=attempt,
        )

    raise last_timeout or ModelTimeoutError("Ollama did not answer.")
