"""``marge serve`` — run the validation portal API locally (spec 16)."""

from __future__ import annotations

import argparse
import sys


def serve(args: argparse.Namespace) -> int:
    """Serve the portal API and the static portal (uvicorn)."""
    try:
        import uvicorn
    except ModuleNotFoundError:
        print("uvicorn is required: python3 -m pip install --user uvicorn", file=sys.stderr)
        return 2

    from marge.api import create_app
    from marge.store import open_store

    store = open_store(args.db)
    app = create_app(store=store, auth_mode=args.auth_mode)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", default="marge.sqlite3", help="sqlite file")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--auth-mode",
        default="dev",
        choices=("dev", "cognito"),
        help="dev trusts X-Actor-* headers, cognito verifies the JWT",
    )


COMMANDS = {"serve": serve}
