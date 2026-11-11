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

from fastapi import FastAPI

from ..domain import Settings
from ..store.base import Store
from .auth import AuthMode, CognitoConfig
from .routes_admin import router as admin_router
from .routes_validation import router as validation_router

APP_TITLE = "Marge — validation portal API"
APP_VERSION = "0.1.0"


def create_app(
    store: Store,
    settings: Settings | None = None,
    auth_mode: AuthMode | str = AuthMode.DEV,
    *,
    cognito_config: CognitoConfig | None = None,
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
    return app
