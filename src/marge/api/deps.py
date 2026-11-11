"""Dependency injection for the FastAPI application (spec 16).

Provides the per-request ``ApiContext`` holding the store, the resolved
actor and the active settings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Header, HTTPException, Request

from ..domain import Settings
from ..store.base import Store
from .auth import Actor, AuthError, AuthMode, CognitoConfig, resolve_actor


@dataclass(slots=True)
class ApiContext:
    """Carried through FastAPI dependencies to every route handler."""

    store: Store
    actor: Actor
    settings: Settings
    auth_mode: AuthMode


def _extract_headers(request: Request) -> dict[str, str]:
    return dict(request.headers.items())


def get_context(
    request: Request,
    authorization: str | None = Header(default=None),
    x_actor_id: str | None = Header(default=None, alias="X-Actor-Id"),
    x_actor_role: str | None = Header(default=None, alias="X-Actor-Role"),
) -> ApiContext:
    """FastAPI dependency resolving the store, settings and authenticated actor."""
    app_state: Any = request.app.state
    store: Store = app_state.store
    settings: Settings = app_state.settings
    auth_mode: AuthMode = app_state.auth_mode
    cognito_config: CognitoConfig | None = getattr(app_state, "cognito_config", None)

    headers = _extract_headers(request)
    if authorization:
        headers["Authorization"] = authorization
    if x_actor_id:
        headers["X-Actor-Id"] = x_actor_id
    if x_actor_role:
        headers["X-Actor-Role"] = x_actor_role

    try:
        actor = resolve_actor(auth_mode, headers, config=cognito_config)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return ApiContext(
        store=store,
        actor=actor,
        settings=settings,
        auth_mode=auth_mode,
    )
