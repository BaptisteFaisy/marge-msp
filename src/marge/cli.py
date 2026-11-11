"""Command line entry point: ``python3 -m marge.cli <command>``.

Kept thin on purpose: every command lives in its own module under
``marge.commands`` and registers itself through ``COMMANDS``. This file only
discovers them, so adding a command never touches the dispatcher and the CLI
stays under the size limits.
"""

from __future__ import annotations

import argparse
import importlib
import pkgutil
import sys

import marge.commands as _commands_pkg

BUILTIN_COMMANDS: dict[str, object] = {}


def discover_commands() -> dict[str, object]:
    """Collect ``COMMANDS`` from every module of ``marge.commands``."""
    found: dict[str, object] = {}
    for module in pkgutil.iter_modules(_commands_pkg.__path__):
        try:
            loaded = importlib.import_module(f"marge.commands.{module.name}")
        except ImportError as exc:  # optional dependency missing (boto3, yaml…)
            print(f"command module {module.name} ignoré : {exc}", file=sys.stderr)
            continue
        for name, handler in getattr(loaded, "COMMANDS", {}).items():
            found[name] = handler
    return found


def _add_subcommand(sub: argparse._SubParsersAction, name: str, handler: object) -> None:
    entry = sub.add_parser(name, help=getattr(handler, "__doc__", "") or "")
    configure = getattr(handler, "configure", None)
    if callable(configure):
        configure(entry)
    entry.set_defaults(handler=handler)


def build_parser(commands: dict[str, object] | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="marge", description="Marge — per-client MSP profitability")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, handler in sorted((commands if commands is not None else discover_commands()).items()):
        _add_subcommand(sub, name, handler)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    handler = args.handler
    if callable(handler):
        return int(handler(args))
    run = getattr(handler, "run", None)
    return int(run(args)) if callable(run) else 1


if __name__ == "__main__":
    raise SystemExit(main())
