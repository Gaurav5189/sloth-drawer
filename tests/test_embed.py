"""The embedder client shapes, without a live Ollama.

Embeddings are the only other thing besides chunk text that crosses the cloud
boundary, so the client's contract — one vector per text, in order, errors as
typed exceptions — is worth pinning down before anything depends on it.
"""

from __future__ import annotations

import pytest

import sloth_drawer.extract.embed as embed_module
from sloth_drawer.errors import OllamaUnavailableError
from sloth_drawer.extract.embed import BATCH_TEXTS, embed


class FakeServer:
    """Counts calls and returns whatever the test queued."""

    def __init__(self, documents):
        self.documents = list(documents)
        self.payloads: list[dict] = []

    def __call__(self, host, path, payload, timeout):
        assert isinstance(host, str)
        assert isinstance(timeout, float)
        assert path == "/api/embed"
        self.payloads.append(dict(payload))
        if not self.documents:
            raise AssertionError("no reply queued")
        return self.documents.pop(0), 0.01


def test_one_vector_per_text_in_order(monkeypatch) -> None:
    fake = FakeServer([{"embeddings": [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]}])
    monkeypatch.setattr(embed_module, "post_json", fake)
    reply = embed(["a", "b", "c"], model="nomic-embed-text", host="http://localhost:11434")
    assert [len(v) for v in reply.vectors] == [2, 2, 2]
    assert reply.vectors[2][0] == pytest.approx(0.5)


def test_batches_are_size_limited(monkeypatch) -> None:
    documents = [
        {"embeddings": [[1, 2, 3]] * BATCH_TEXTS},
        {"embeddings": [[4, 5, 6]] * 3},
    ]  # 32 + 3 = 35 texts over two calls
    fake = FakeServer(documents)
    monkeypatch.setattr(embed_module, "post_json", fake)
    reply = embed(["t"] * 35, model="m", host="h")
    assert len(reply.vectors) == 35
    assert len(fake.payloads) == 2
    assert len(fake.payloads[0]["input"]) == BATCH_TEXTS
    assert len(fake.payloads[1]["input"]) == 3


def test_a_bad_reply_is_a_typed_error(monkeypatch) -> None:
    fake = FakeServer([{"embeddings": [[0.1]]}])  # two texts asked, one returned
    monkeypatch.setattr(embed_module, "post_json", fake)
    with pytest.raises(OllamaUnavailableError):
        embed(["a", "b"], model="m", host="h")


def test_an_empty_ask_costs_nothing(monkeypatch) -> None:
    fake = FakeServer([])
    monkeypatch.setattr(embed_module, "post_json", fake)
    assert embed([], model="m", host="h").vectors == []
    assert fake.payloads == []
