"""``marge mcp`` — run the MCP action server on stdio (spec 14.3)."""

from __future__ import annotations

import argparse
import json
import sys


def mcp(args: argparse.Namespace) -> int:
    """Serve the MCP tools over stdin/stdout (JSON-RPC 2.0, one message per line)."""
    from marge.api.deps import build_local_store
    from marge.mcp.server import McpContext, serve_stdio

    store = build_local_store(args.db)
    ctx = McpContext(store=store, actor_id=args.actor, role=args.role)
    if args.self_test:
        from marge.mcp.server import handle_request

        response = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, ctx)
        print(json.dumps(response, indent=2, ensure_ascii=False))
        return 0
    return int(serve_stdio(ctx, sys.stdin, sys.stdout))


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", default="marge.sqlite3")
    parser.add_argument("--actor", default="controller-01")
    parser.add_argument("--role", default="CONTROLLER")
    parser.add_argument("--self-test", action="store_true", help="print tools/list and exit")


COMMANDS = {"mcp": mcp}
