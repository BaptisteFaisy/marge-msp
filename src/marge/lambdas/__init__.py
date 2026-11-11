"""Lambda handlers of Marge (spec 11.2).

Every handler is a thin adapter: the logic lives in ``marge.api``,
``marge.contracts``, ``marge.classify``, ``marge.mcp``, ``marge.pipeline`` and
``marge.publish``, so the deployed stack and the local CLI run the same code.
"""

from __future__ import annotations

from .asgi import build_scope, handle
from .handlers import classify_handler, contracts_handler, mcp_handler, portal_handler
from .jobs import monthly_handler, nightly_handler, publish_handler, weekly_handler

__all__ = [
    "build_scope",
    "classify_handler",
    "contracts_handler",
    "handle",
    "mcp_handler",
    "monthly_handler",
    "nightly_handler",
    "portal_handler",
    "publish_handler",
    "weekly_handler",
]
