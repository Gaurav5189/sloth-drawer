"""The ASGI entry a web platform can point at directly.

``uvicorn sloth_drawer.webapp:app`` — one module-level ``app`` built from the
ambient ``SLOTH_HOME``. Web *platforms* (Render's Docker runtime, a bare
``uvicorn`` invocation) have no CLI parser, so this module does the same thing
``sloth_drawer.cli._cmd_serve`` does: read the config, refuse to boot without
scan data, and hand a fully bound ``web.app.create_app`` over. The ASGI
surface itself still lives in ``web/`` (imports storage + render + errors
only); this module is a sibling of ``cli.py`` and may import ``config``.
"""

from __future__ import annotations

from sloth_drawer.config import load_config
from sloth_drawer.errors import ConfigError
from sloth_drawer.web.app import create_app

_config = load_config()

if not _config.paths.db.is_file():
    raise ConfigError(
        f"No scan data at {_config.paths.db} in SLOTH_HOME={_config.paths.root}. "
        "Run `sloth-drawer scan <dir>` first, or deploy with the seed snapshot "
        "(see deploy/Containerfile)."
    )

#: The module-level ASGI application.
app = create_app(_config.paths.db, _config.paths.devices_toml)
