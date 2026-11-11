"""FastAPI validation portal (spec 16).

Exposes exactly the routes of chapter 16, resolves the actor's role from the
request token (``auth``), applies row-level filtering (``rls``) and writes an
``AuditEntry`` for every decision (EF-VAL-02).

Third-party imports (fastapi, pydantic) stay inside this package: ``domain``
and ``calc`` remain standard-library only, and boto3 is never imported here.
"""

from __future__ import annotations

from .app import create_app
from .auth import Actor, AuthError, AuthMode, CognitoConfig, resolve_actor
from .deps import ApiContext, get_context
from .recalculate import run_recalculate
from .rls import (
    can_access_client,
    filter_by_clients,
    redact_contract_for_actor,
    redact_rates_for_actor,
    redact_row,
    row_filter,
    visible_client_ids,
)

__all__ = [
    "Actor",
    "ApiContext",
    "AuthError",
    "AuthMode",
    "CognitoConfig",
    "can_access_client",
    "create_app",
    "filter_by_clients",
    "get_context",
    "redact_contract_for_actor",
    "redact_rates_for_actor",
    "redact_row",
    "resolve_actor",
    "row_filter",
    "run_recalculate",
    "visible_client_ids",
]
