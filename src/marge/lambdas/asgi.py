"""API Gateway (REST, payload v1) to ASGI adapter, standard library only.

The portal API is a FastAPI/Starlette application. Lambda runs WSGI-free and
has no server, so this module drives the ASGI app through one request: it
builds the scope from the API Gateway event, runs the app on an event loop and
collects the response back into the proxy integration shape.

No third-party bridge (mangum, awslambdaproxy): the Lambda runtime would need
an extra layer for it, and the adapter is small enough to test directly.
"""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlencode


def _headers(event: dict[str, Any]) -> list[tuple[bytes, bytes]]:
    """ASGI header pairs, lower-cased names, multi-value aware."""
    pairs: list[tuple[bytes, bytes]] = []
    for name, value in (event.get("headers") or {}).items():
        if value is not None:
            pairs.append((name.lower().encode(), str(value).encode()))
    for name, values in (event.get("multiValueHeaders") or {}).items():
        for value in values or []:
            pairs.append((name.lower().encode(), str(value).encode()))
    return pairs


def _query_string(event: dict[str, Any]) -> bytes:
    multi = event.get("multiValueQueryStringParameters") or {}
    if multi:
        return urlencode([(key, value) for key, values in multi.items() for value in values or []]).encode()
    single = event.get("queryStringParameters") or {}
    return urlencode(single).encode()


def _body(event: dict[str, Any]) -> bytes:
    raw = event.get("body") or ""
    if isinstance(raw, bytes):
        return raw if not event.get("isBase64Encoded") else _b64decode(raw)
    if event.get("isBase64Encoded"):
        return _b64decode(raw)
    return raw.encode("utf-8")


def _b64decode(raw: Any) -> bytes:
    import base64

    return base64.b64decode(raw if isinstance(raw, bytes) else raw.encode("ascii"))


def build_scope(event: dict[str, Any]) -> dict[str, Any]:
    """The ASGI scope of one API Gateway REST (payload v1) event."""
    context = event.get("requestContext") or {}
    identity = context.get("identity") or {}
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": event.get("httpMethod") or "GET",
        "path": event.get("path") or "/",
        "raw_path": (event.get("path") or "/").encode(),
        "root_path": context.get("path") or "",
        "scheme": "https",
        "query_string": _query_string(event),
        "headers": _headers(event),
        "client": (identity.get("sourceIp"), 0) if identity.get("sourceIp") else None,
        "server": ("lambda", 443),
        "aws_event": event,
    }


async def _run(app: Any, scope: dict[str, Any], payload: bytes) -> dict[str, Any]:
    """Drive the ASGI app and collect its response."""
    response: dict[str, Any] = {"statusCode": 500, "headers": {}, "body": "", "isBase64Encoded": False}
    chunks: list[bytes] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": payload, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            response["statusCode"] = message["status"]
            response["headers"] = {
                name.decode(): value.decode() for name, value in message.get("headers", [])
            }
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b"") or b"")

    await app(scope, receive, send)
    body = b"".join(chunks)
    content_type = response["headers"].get("content-type", "")
    if content_type.startswith("text/") or "json" in content_type:
        response["body"] = body.decode("utf-8", errors="replace")
    else:
        import base64

        response["body"] = base64.b64encode(body).decode("ascii")
        response["isBase64Encoded"] = True
    return response


def handle(app: Any, event: dict[str, Any]) -> dict[str, Any]:
    """Synchronous entry point used by every Lambda handler.

    A fresh loop per invocation: Lambda containers are reused across requests
    and a cached loop can be closed or already running, which
    ``asyncio.get_event_loop`` reports as a deprecation instead of handling.
    """
    scope = build_scope(event)
    payload = _body(event)
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_run(app, scope, payload))
    finally:
        loop.close()
