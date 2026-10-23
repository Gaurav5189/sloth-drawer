"""The FastAPI application factory for the web surface.

Deliberately minimal: one router, typed-error handlers, no sessions, no
JavaScript, no templating engine beyond Python f-strings (RULES.md 1.1).
Free-tier cold starts boot a single process from this module — anything it
touches at import time costs seconds, which no demo can spare.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.exceptions import HTTPException
from starlette.requests import Request

import sloth_drawer.errors as errors
from sloth_drawer.web import page
from sloth_drawer.web.routes import build_router


def create_app(db_path: Path, devices_toml: Path) -> FastAPI:
    """The app, bound to the state paths the caller (the CLI) resolved."""
    app = FastAPI(title="Sloth Drawer", docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(build_router(db_path, devices_toml))

    caught: dict[type[Exception], tuple[int, str]] = {
        errors.ConfigError: (404, "Not configured"),
        errors.StorageError: (503, "The storage is unavailable"),
    }

    @app.exception_handler(HTTPException)
    async def _http_exception(_request: Request, exc: HTTPException) -> HTMLResponse:
        return HTMLResponse(page.error_page(exc.status_code, _title(exc.status_code), exc.detail),
                            status_code=exc.status_code)

    @app.exception_handler(errors.SlothDrawerError)
    async def _domain_exception(_request: Request, exc: errors.SlothDrawerError) -> HTMLResponse:
        status, title = caught.get(type(exc), (500, "The drawer hit an error"))
        print(f"web: {type(exc).__name__}: {exc}", file=sys.stderr)
        return HTMLResponse(page.error_page(status, title, str(exc)), status_code=status)

    @app.exception_handler(Exception)
    async def _unhandled(_request: Request, exc: Exception) -> HTMLResponse:
        # A failure that reaches this handler is never silent: the traceback
        # goes to the server log (uvicorn) and the user gets a word, not a
        # blank screen (RULES.md 2.4a).
        print(f"web: unhandled {type(exc).__name__}: {exc}", file=sys.stderr)
        return HTMLResponse(
            page.error_page(500, "The drawer hit an error", "The trace is in the server log."),
            status_code=500,
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        """For a platform's liveness probe: state-free and instant."""
        return {"status": "ok"}

    return app


def _title(status: int) -> str:
    if status == 404:
        return "Nothing in this drawer slot"
    if status >= 500:
        return "The drawer hit an error"
    return "Something is off"
