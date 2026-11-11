"""FastAPI application factory (spec 16).

``create_app(store, settings, auth_mode)`` wires the exact route table of
chapter 16 — nothing more — on top of any ``Store`` implementation:

    GET  /v1/matches                              POST /v1/matches/{id}/decision
    GET  /v1/contracts                            GET  /v1/contracts/{id}
    PUT  /v1/contracts/{id}/fields                POST /v1/contracts/{id}/validate
    GET  /v1/classifications?status=pending       POST /v1/classifications/{id}/decision
    GET  /v1/rates                                PUT  /v1/rates
    GET  /v1/allocation-rules                     PUT  /v1/allocation-rules
    GET  /v1/coverage                             POST /v1/recalculate
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ..domain import Settings
from ..store.base import Store
from .auth import AuthMode, CognitoConfig
from .routes_admin import router as admin_router
from .routes_auth import router as auth_router
from .routes_insight import router as insight_router
from .routes_validation import router as validation_router

APP_TITLE = "Marge — validation portal API"
APP_VERSION = "0.1.0"
DEFAULT_PORTAL_DIR = Path(__file__).resolve().parents[3] / "portal"


def create_app(
    store: Store,
    settings: Settings | None = None,
    auth_mode: AuthMode | str = AuthMode.DEV,
    *,
    cognito_config: CognitoConfig | None = None,
    portal_dir: str | Path | None = None,
) -> FastAPI:
    """Build the portal API over ``store``.

    ``auth_mode`` selects how the caller is identified: ``dev`` trusts the
    ``X-Actor-Id``/``X-Actor-Role`` headers (demo portal, EF-ADM-03);
    ``cognito`` verifies a signed JWT and refuses every token when no
    verification key is configured (spec 17).
    """
    app = FastAPI(title=APP_TITLE, version=APP_VERSION)
    app.state.store = store
    app.state.settings = settings if settings is not None else store.load()
    app.state.auth_mode = AuthMode(str(auth_mode))
    app.state.cognito_config = cognito_config
    app.include_router(validation_router)
    app.include_router(admin_router)
    app.include_router(insight_router)
    app.include_router(auth_router)
    mount_portal(app, portal_dir)
    return app


def mount_portal(app: FastAPI, portal_dir: str | Path | None = None) -> Path | None:
    """Serve the static validation portal next to the JSON API (EF-VAL-01).

    Mounted last, on ``/``: the ``/v1/*`` routers registered above keep
    priority, so the API and the single-page portal share one origin — which is
    what the demo URL given to the judges needs. A missing directory is not an
    error: the API still runs headless.
    """
    directory = Path(portal_dir) if portal_dir else DEFAULT_PORTAL_DIR
    if not (directory / "index.html").is_file():
        return None
    app.mount("/", StaticFiles(directory=str(directory), html=True), name="portal")
    return directory
