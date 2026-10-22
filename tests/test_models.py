"""Tests for the model registry and the Ollama reachability checks."""

from __future__ import annotations

import json
import socket
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from sloth_drawer.errors import ConfigError, OllamaUnavailableError
from sloth_drawer.models import (
    DEFAULT_EMBEDDER,
    DEFAULT_EXTRACTOR,
    DEFAULT_TRIAGE,
    check_model_pulled,
    check_ollama,
    is_available,
    model_registry,
    require_model,
)


class _TagsHandler(BaseHTTPRequestHandler):
    """A stand-in for the local Ollama server."""

    payload = {"models": [{"name": "gemma3:1b"}, {"name": "phi4-mini:latest"}]}

    def do_GET(self) -> None:  # noqa: N802 - the stdlib names it this way
        if self.path != "/api/tags":
            self.send_error(404)
            return
        body = json.dumps(self.payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        """Keep the test output quiet."""


@pytest.fixture
def ollama_stub() -> Iterator[str]:
    """A local HTTP server that answers ``/api/tags`` like Ollama does."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _TagsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def closed_port() -> str:
    """A loopback address nothing is listening on."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    return f"http://127.0.0.1:{port}"


def test_the_registry_holds_every_model_with_its_measured_numbers() -> None:
    registry = {spec.model_id: spec for spec in model_registry()}
    assert set(registry) == {
        DEFAULT_TRIAGE,
        DEFAULT_EXTRACTOR,
        "phi4-mini:latest",
        DEFAULT_EMBEDDER,
    }
    assert registry[DEFAULT_EXTRACTOR].size_mb == 806
    assert registry[DEFAULT_TRIAGE].size_mb == 291
    assert registry["phi4-mini:latest"].size_display == "2.5 GB"


def test_check_ollama_lists_the_pulled_models(ollama_stub: str) -> None:
    assert check_ollama(ollama_stub) == ["gemma3:1b", "phi4-mini:latest"]


def test_an_unreachable_server_fails_fast_with_the_fix(closed_port: str) -> None:
    with pytest.raises(OllamaUnavailableError) as caught:
        check_ollama(closed_port, timeout=2.0)
    assert 'Start it with "ollama serve"' in str(caught.value)


def test_check_model_pulled(ollama_stub: str) -> None:
    assert check_model_pulled("gemma3:1b", ollama_stub) is True
    assert check_model_pulled("gemma3:270m", ollama_stub) is False


def test_a_missing_model_names_the_pull_command(ollama_stub: str) -> None:
    with pytest.raises(ConfigError) as caught:
        require_model("gemma3:270m", ollama_stub)
    message = str(caught.value)
    assert 'Model "gemma3:270m" is not pulled.' in message
    assert "ollama pull gemma3:270m" in message


def test_tags_are_optional_but_the_base_name_is_not_enough() -> None:
    assert is_available("phi4-mini", ["phi4-mini:latest"]) is True
    assert is_available("phi4-mini:latest", ["phi4-mini"]) is True
    assert is_available("gemma3:1b", ["gemma3:270m"]) is False
    assert is_available("gemma3:1b", ["gemma3:1b", "gemma3:270m"]) is True
