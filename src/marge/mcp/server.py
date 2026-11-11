"""MCP server: JSON-RPC 2.0 over stdio (spec 14.3, MCP glossary).

Minimal but correct: ``initialize``, ``tools/list``, ``tools/call`` and the
notification shape. Any other method answers ``-32601`` (method not found).
Nothing here talks to a model: the tools read the store and, at most, call the
ticket tool.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from ..domain import ActorRole
from ..store.base import Store

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "marge-mcp", "version": "0.1.0"}


@dataclass(slots=True)
class Tool:
    """One callable tool, with its JSON schema."""

    name: str
    description: str
    input_schema: dict
    handler: Callable[[McpContext, dict], dict]


@dataclass(slots=True)
class McpContext:
    """Everything a tool may use, injected (no global state)."""

    store: Store
    actor_id: str = "controller-01"
    role: ActorRole = ActorRole.CONTROLLER
    itsm: Any = None
    settings: Any = None
    extra: dict = field(default_factory=dict)


def _error(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _result(request_id: Any, payload: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}


def tools() -> tuple[Tool, ...]:
    """The three tools of spec 14.3 (imported lazily to avoid a cycle)."""
    from .tools import TOOLS

    return TOOLS


def handle_request(payload: dict, ctx: McpContext) -> dict:
    """Handle one JSON-RPC message and return the response object."""
    request_id = payload.get("id")
    method = payload.get("method", "")
    params = payload.get("params") or {}

    if method == "initialize":
        return _result(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "serverInfo": SERVER_INFO,
                "capabilities": {"tools": {"listChanged": False}},
            },
        )
    if method == "tools/list":
        return _result(
            request_id,
            {
                "tools": [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.input_schema,
                    }
                    for tool in tools()
                ]
            },
        )
    if method == "tools/call":
        return _call_tool(request_id, params, ctx)
    if method in ("notifications/initialized", "ping"):
        return _result(request_id, {})
    return _error(request_id, -32601, f"method not found: {method}")


def _call_tool(request_id: Any, params: dict, ctx: McpContext) -> dict:
    name = params.get("name", "")
    arguments = params.get("arguments") or {}
    for tool in tools():
        if tool.name != name:
            continue
        try:
            result = tool.handler(ctx, arguments)
        except (ValueError, PermissionError, LookupError) as exc:
            return _error(request_id, -32000, str(exc))
        return _result(
            request_id,
            {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}]},
        )
    return _error(request_id, -32602, f"unknown tool: {name}")


def serve_stdio(ctx: McpContext, reader: Iterable[str], writer) -> int:
    """Read one JSON message per line, write one response per line."""
    for line in reader:
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            writer.write(json.dumps(_error(None, -32700, "parse error")) + "\n")
            writer.flush()
            continue
        response = handle_request(payload, ctx)
        if payload.get("id") is None:
            continue
        writer.write(json.dumps(response, ensure_ascii=False, default=str) + "\n")
        writer.flush()
    return 0
