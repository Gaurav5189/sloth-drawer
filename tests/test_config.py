"""Tests for path resolution, the loopback guard and backend selection."""

from __future__ import annotations

from pathlib import Path

import pytest

from sloth_drawer.config import (
    DEFAULT_EMBED_DIMS,
    DEFAULT_EMBED_MODEL,
    DEFAULT_OLLAMA_HOST,
    PROMPT_VERSION,
    Config,
    Paths,
    load_config,
    redact_dsn,
)
from sloth_drawer.errors import ConfigError


def test_paths_hang_off_one_root(tmp_path) -> None:
    paths = Paths(root=tmp_path)
    assert paths.manuals == tmp_path / "data" / "manuals"
    assert paths.devices_toml == tmp_path / "data" / "devices.toml"
    assert paths.db == tmp_path / "out" / "sloth.db"
    assert paths.cards == tmp_path / "out" / "cards"
    assert paths.report_md == tmp_path / "out" / "report.md"


def test_defaults_need_no_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "SLOTH_DATABASE_URL",
        "SLOTH_EMBED_MODEL",
        "SLOTH_EMBED_DIMS",
        "SLOTH_SENTRY_DSN",
        "SLOTH_OLLAMA_HOST",
        "SLOTH_RETRIEVAL",
        "SLOTH_HOME",
    ):
        monkeypatch.delenv(name, raising=False)

    config = load_config()
    assert config.ollama_host == DEFAULT_OLLAMA_HOST
    assert config.embed_model == DEFAULT_EMBED_MODEL
    assert config.embed_dims == DEFAULT_EMBED_DIMS
    assert config.retrieval == "local"
    assert config.database_url is None
    assert config.sentry_dsn is None


def test_a_dsn_selects_the_tiger_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SLOTH_RETRIEVAL", raising=False)
    monkeypatch.setenv("SLOTH_DATABASE_URL", "postgresql://u:p@host:5432/db")
    config = load_config()
    assert config.retrieval == "tiger"
    assert config.use_tiger is True


def test_the_backend_can_be_forced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLOTH_RETRIEVAL", "local")
    monkeypatch.setenv("SLOTH_DATABASE_URL", "postgresql://u:p@host:5432/db")
    assert load_config().retrieval == "local"

    monkeypatch.setenv("SLOTH_RETRIEVAL", "tiger")
    monkeypatch.delenv("SLOTH_DATABASE_URL")
    assert load_config().retrieval == "tiger"


def test_an_unknown_backend_is_a_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLOTH_RETRIEVAL", "pinecone")
    with pytest.raises(ConfigError, match="SLOTH_RETRIEVAL"):
        load_config()


@pytest.mark.parametrize(
    "host",
    ["http://192.168.1.10:11434", "http://ollama.example.com:11434", "https://10.0.0.1"],
)
def test_a_non_loopback_ollama_host_is_refused(monkeypatch: pytest.MonkeyPatch, host: str) -> None:
    monkeypatch.setenv("SLOTH_OLLAMA_HOST", host)
    with pytest.raises(ConfigError, match="loopback"):
        load_config()


@pytest.mark.parametrize(
    "host",
    ["http://localhost:11434", "http://127.0.0.1:11434", "http://[::1]:11434", "127.0.0.1:11434"],
)
def test_loopback_hosts_are_accepted(monkeypatch: pytest.MonkeyPatch, host: str) -> None:
    monkeypatch.setenv("SLOTH_OLLAMA_HOST", host)
    assert load_config().ollama_host == host


def test_a_bad_embedding_width_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLOTH_EMBED_DIMS", "not-a-number")
    with pytest.raises(ConfigError, match="SLOTH_EMBED_DIMS"):
        load_config()


def test_the_dsn_password_never_leaks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLOTH_DATABASE_URL", "postgresql://user:hunter2@db.host:5432/sloth")
    config = load_config()
    assert "hunter2" not in config.redacted_database_url
    assert "user:***@db.host:5432" in config.redacted_database_url
    assert config.database_url is not None  # the real DSN stays in memory only


def test_redact_dsn_leaves_a_bare_url_alone() -> None:
    assert redact_dsn("postgresql://host:5432/db") == "postgresql://host:5432/db"


def test_prompt_version_is_exported() -> None:
    assert PROMPT_VERSION == 1


def test_config_is_immutable() -> None:
    config = Config(
        paths=Paths(root=Path("/tmp")),
        ollama_host=DEFAULT_OLLAMA_HOST,
        ollama_timeout=1.0,
        retrieval="local",
        database_url=None,
        embed_model=DEFAULT_EMBED_MODEL,
        embed_dims=DEFAULT_EMBED_DIMS,
        sentry_dsn=None,
    )
    with pytest.raises(AttributeError):
        config.retrieval = "tiger"  # type: ignore[misc]
