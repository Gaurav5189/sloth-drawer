"""Paths, environment overrides, and the loopback guard.

The product must work with **zero configuration**: no environment variable, no
config file, no account. Every value here therefore has a default that is
correct on a plain laptop with a local Ollama. Environment variables only ever
*override* a default (RULES.md 1.3).

Two things are deliberately not configurable:

*   the Ollama host must resolve to a loopback address (C6 — the model path may
    not talk to the network), and
*   the retrieval backend is chosen by configuration, never by a conditional in
    the pipeline, so the choice lives here and nowhere else.
"""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from sloth_drawer.errors import ConfigError

#: Default Ollama base URL. Loopback only.
DEFAULT_OLLAMA_HOST = "http://localhost:11434"

#: Per-call timeout for a model request, in seconds (RULES.md 2.3).
DEFAULT_OLLAMA_TIMEOUT = 120.0

#: Default embedding model and its width. The width must match the ``vector(N)``
#: column in ``vector/schema.sql``; a mismatch is a startup error.
DEFAULT_EMBED_MODEL = "nomic-embed-text"
DEFAULT_EMBED_DIMS = 768

#: Bumped whenever a prompt changes, so a stored interval stays reproducible
#: (RULES.md 3.4). ``extract.prompts`` re-exports this name.
PROMPT_VERSION = 1

#: The two retrieval backends. Both implement the same ``Retriever`` interface.
RETRIEVAL_BACKENDS = ("local", "tiger")

#: Environment variable that pins the project root when the package is installed
#: outside a checkout (e.g. a container with a mounted data directory).
HOME_ENV = "SLOTH_HOME"


def _find_project_root() -> Path:
    """Locate the project root without hardcoding an absolute path.

    A checkout (editable install) is found by walking up from this file until a
    ``pyproject.toml`` appears. An installed wheel has no such marker, so the
    working directory is the next best answer.
    """
    override = os.environ.get(HOME_ENV)
    if override:
        return Path(override).expanduser().resolve()

    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return Path.cwd().resolve()


@dataclass(frozen=True)
class Paths:
    """Every filesystem location the tool uses, derived from one root."""

    root: Path

    @property
    def data(self) -> Path:
        """The hand-edited input directory: device registry and manuals."""
        return self.root / "data"

    @property
    def manuals(self) -> Path:
        """The user's manual PDFs. Never committed."""
        return self.data / "manuals"

    @property
    def devices_toml(self) -> Path:
        """The device registry read with stdlib ``tomllib``."""
        return self.data / "devices.toml"

    @property
    def out(self) -> Path:
        """Everything generated lives here and is gitignored."""
        return self.root / "out"

    @property
    def cards(self) -> Path:
        """Rendered cards, one file per device."""
        return self.out / "cards"

    @property
    def db(self) -> Path:
        """The local SQLite state: devices, intervals, service events, FTS index."""
        return self.out / "sloth.db"

    @property
    def report_json(self) -> Path:
        return self.out / "report.json"

    @property
    def report_md(self) -> Path:
        return self.out / "report.md"


@dataclass(frozen=True)
class Config:
    """The resolved configuration for one run."""

    paths: Paths
    ollama_host: str
    ollama_timeout: float
    retrieval: str
    database_url: str | None
    embed_model: str
    embed_dims: int
    sentry_dsn: str | None

    @property
    def use_tiger(self) -> bool:
        """True when the cloud retrieval backend is selected."""
        return self.retrieval == "tiger"

    @property
    def redacted_database_url(self) -> str:
        """The DSN with its password masked, safe for logs and reports."""
        if not self.database_url:
            return ""
        return redact_dsn(self.database_url)


def redact_dsn(dsn: str) -> str:
    """Mask the password in a Postgres DSN.

    A DSN is a secret. It must never reach a log line, an error message or a
    report, so every place that prints one uses this (RULES.md 2.4a).
    """
    parts = urlsplit(dsn)
    if not parts.netloc or "@" not in parts.netloc:
        return dsn
    userinfo, _, host = parts.netloc.rpartition("@")
    user = userinfo.split(":", 1)[0]
    return urlunsplit(parts._replace(netloc=f"{user}:***@{host}"))


def _require_loopback(host: str) -> str:
    """Reject any Ollama host that is not on this machine.

    The model path must never make a network call (C6). Rather than trusting a
    hostname, only a literal loopback address or ``localhost`` is accepted, so
    the check cannot be defeated by a DNS entry that resolves off-box.
    """
    candidate = host if "://" in host else f"http://{host}"
    parts = urlsplit(candidate)
    if parts.scheme not in ("http", "https"):
        raise ConfigError(
            f"Ollama host {host!r} uses scheme {parts.scheme!r}. Use an http:// or https:// URL."
        )
    hostname = parts.hostname
    if not hostname:
        raise ConfigError(f"Ollama host {host!r} has no hostname.")

    if hostname.lower() in ("localhost", "localhost.localdomain"):
        return host

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError as exc:
        raise ConfigError(
            f"Ollama host {hostname!r} is not a loopback address. "
            f"Sloth Drawer runs inference on this machine; point it at "
            f"{DEFAULT_OLLAMA_HOST} (or another 127.0.0.1 / ::1 address)."
        ) from exc

    if not address.is_loopback:
        raise ConfigError(
            f"Ollama host {hostname!r} is not a loopback address. "
            f"Sloth Drawer runs inference on this machine; point it at "
            f"{DEFAULT_OLLAMA_HOST} (or another 127.0.0.1 / ::1 address)."
        )
    return host


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}.") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be a positive integer, got {value}.")
    return value


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}.") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be positive, got {value}.")
    return value


def _select_retrieval(database_url: str | None) -> str:
    """Pick the retrieval backend from configuration only.

    There is no ``if backend ==`` in the pipeline: the decision is made here,
    once, and the resulting object is injected (RULES.md 6).
    """
    forced = os.environ.get("SLOTH_RETRIEVAL", "").strip().lower()
    if forced:
        if forced not in RETRIEVAL_BACKENDS:
            raise ConfigError(
                f"SLOTH_RETRIEVAL must be one of {', '.join(RETRIEVAL_BACKENDS)}, got {forced!r}."
            )
        return forced
    return "tiger" if database_url else "local"


def load_config(root: Path | None = None) -> Config:
    """Build the configuration for this run.

    Raises :class:`ConfigError` for anything unusable — the CLI turns that into
    exit code 2 with a message that says what to do next.
    """
    paths = Paths(root=root.resolve() if root else _find_project_root())

    ollama_host = os.environ.get("SLOTH_OLLAMA_HOST", "").strip() or DEFAULT_OLLAMA_HOST
    ollama_host = _require_loopback(ollama_host)

    database_url = os.environ.get("SLOTH_DATABASE_URL", "").strip() or None
    retrieval = _select_retrieval(database_url)

    embed_dims = _env_int("SLOTH_EMBED_DIMS", DEFAULT_EMBED_DIMS)
    embed_model = os.environ.get("SLOTH_EMBED_MODEL", "").strip() or DEFAULT_EMBED_MODEL
    sentry_dsn = os.environ.get("SLOTH_SENTRY_DSN", "").strip() or None

    return Config(
        paths=paths,
        ollama_host=ollama_host,
        ollama_timeout=_env_float("SLOTH_OLLAMA_TIMEOUT", DEFAULT_OLLAMA_TIMEOUT),
        retrieval=retrieval,
        database_url=database_url,
        embed_model=embed_model,
        embed_dims=embed_dims,
        sentry_dsn=sentry_dsn,
    )
