"""The model registry and the checks that keep the model layer honest.

The registry is **data**, not prose: the sizes and latencies below are the
numbers measured on the reference box (4 cores, 7.5 GB RAM, no GPU) by
``bench/``. Keeping them in one table means the post, the CLI and the code
cannot drift apart (RULES.md 1.4, ARCHITECTURE.md 4.4).

Nothing in this module infers anything. It only describes the models and asks
the local server what it has.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from sloth_drawer.errors import ConfigError, OllamaUnavailableError

#: Default extractor. Chosen because it passed every schema pattern in the
#: benchmark while being a third the size of the alternative.
DEFAULT_EXTRACTOR = "gemma3:1b"

#: Default triage model: cheap yes/no gate in front of the expensive extractor.
DEFAULT_TRIAGE = "gemma3:270m"

#: Default embedding model for the cloud retrieval backend.
DEFAULT_EMBEDDER = "nomic-embed-text"


@dataclass(frozen=True)
class ModelSpec:
    """One row of the registry: what the model is for and what it costs."""

    model_id: str
    role: str
    size_mb: int
    latency_s: str
    tokens_per_s: str
    note: str

    @property
    def size_display(self) -> str:
        """Human-readable size, switching to GB at 1024 MB like a download would."""
        if self.size_mb >= 1024:
            return f"{self.size_mb / 1024:.1f} GB"
        return f"{self.size_mb} MB"


def model_registry() -> tuple[ModelSpec, ...]:
    """Every model this project knows how to drive, with its measured numbers.

    Returned fresh each call so a caller cannot mutate the shared table.
    """
    return (
        ModelSpec(
            model_id=DEFAULT_TRIAGE,
            role="triage",
            size_mb=291,
            latency_s="3.0-6.8 s",
            tokens_per_s="9-16",
            note="yes/no gate only; it gets the interval wrong on its own",
        ),
        ModelSpec(
            model_id=DEFAULT_EXTRACTOR,
            role="extractor (default)",
            size_mb=806,
            latency_s="12-13 s",
            tokens_per_s="4.7-13.4",
            note="one fact per call; passes both schema patterns",
        ),
        ModelSpec(
            model_id="phi4-mini:latest",
            role="extractor (alternative)",
            size_mb=2560,
            latency_s="27-48 s",
            tokens_per_s="1.4-3.5",
            note="documented --model swap; fails the array schema, swaps on 8 GB",
        ),
        ModelSpec(
            model_id=DEFAULT_EMBEDDER,
            role="embedder",
            size_mb=274,
            latency_s="< 1 s",
            tokens_per_s="-",
            note="768 dims, 2K context; used only by the tiger backend",
        ),
    )


def _matches(pulled: str, wanted: str) -> bool:
    """Whether a pulled model id satisfies a requested one.

    Ollama tags are optional, so ``phi4-mini`` and ``phi4-mini:latest`` are the
    same model. The *base* name is never enough on its own: ``gemma3:1b`` and
    ``gemma3:270m`` share a base name and are different models.
    """
    if pulled == wanted:
        return True
    if ":" not in wanted and pulled == f"{wanted}:latest":
        return True
    return wanted.endswith(":latest") and pulled == wanted[: -len(":latest")]


def _ollama_get_json(host: str, path: str, timeout: float) -> object:
    """GET a JSON document from the Ollama server.

    Fails fast and does not retry: if the server is not listening it will not
    start listening in two seconds (RULES.md 2.3).
    """
    url = f"{host.rstrip('/')}{path}"
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        raise OllamaUnavailableError(
            f"Ollama at {host} replied with HTTP {exc.code} for {path}. "
            f'Start it with "ollama serve".'
        ) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise OllamaUnavailableError(
            f'Cannot reach Ollama at {host}. Start it with "ollama serve".'
        ) from exc

    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OllamaUnavailableError(
            f"Ollama at {host} replied with a response that is not JSON. "
            f'Start it with "ollama serve".'
        ) from exc


def check_ollama(host: str, timeout: float = 5.0) -> list[str]:
    """Return the ids of the models the local server has pulled.

    Raises :class:`OllamaUnavailableError` when the server cannot be reached —
    the CLI turns that into exit code 2 with the fix in the message.
    """
    payload = _ollama_get_json(host, "/api/tags", timeout)
    if not isinstance(payload, dict):
        raise OllamaUnavailableError(
            f'Ollama at {host} replied with an unexpected payload. Start it with "ollama serve".'
        )
    models = payload.get("models")
    if not isinstance(models, list):
        return []

    names: list[str] = []
    for entry in models:
        if isinstance(entry, dict):
            name = entry.get("name") or entry.get("model")
            if isinstance(name, str):
                names.append(name)
    return names


def is_available(model_id: str, pulled: list[str]) -> bool:
    """Whether a requested model id is present in a list of pulled model ids."""
    return any(_matches(name, model_id) for name in pulled)


def check_model_pulled(model_id: str, host: str, timeout: float = 5.0) -> bool:
    """Whether ``model_id`` is available on the local server.

    Raises :class:`OllamaUnavailableError` if the server itself is unreachable;
    a reachable server that lacks the model simply returns ``False``.
    """
    return is_available(model_id, check_ollama(host, timeout))


def require_model(model_id: str, host: str, timeout: float = 5.0) -> None:
    """Assert that a model is pulled, with the exact command to fix it.

    Used before a run starts, so the failure is immediate and actionable
    rather than a timeout twenty minutes into a batch (RULES.md 2.3).
    """
    if not check_model_pulled(model_id, host, timeout):
        raise ConfigError(f'Model "{model_id}" is not pulled. Run: ollama pull {model_id}')
