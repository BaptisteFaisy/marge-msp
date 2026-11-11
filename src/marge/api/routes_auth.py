"""Authentication configuration endpoint (idea 61).

The portal is a static page: it cannot know the Cognito client id or the Hosted
UI domain at build time without baking an environment into the bundle. It asks
the API instead, which is served from the same Lambda that already knows.

Nothing secret is returned — an implicit-flow client id is public by design.
When the deployment runs in ``dev`` mode the endpoint says so, and the portal
keeps its actor selector instead of showing a sign-in button.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(prefix="/v1")


@router.get("/auth/config")
def auth_config(request: Request) -> dict[str, Any]:
    """How the portal should authenticate its user.

    Deliberately public: it is bootstrap metadata for a static page that cannot
    know its own deployment, and it carries no secret — an implicit-flow client
    id is public by design. Everything else under ``/v1`` stays authenticated.
    """
    mode = str(request.app.state.auth_mode.value)
    if mode != "cognito":
        return {"mode": mode, "cognito": None}
    return {
        "mode": mode,
        "cognito": {
            "issuer": os.environ.get("MARGE_COGNITO_ISSUER", ""),
            "client_id": os.environ.get("MARGE_COGNITO_CLIENT_ID", ""),
            "domain": os.environ.get("MARGE_COGNITO_DOMAIN", ""),
            "scopes": "openid email profile",
        },
    }
