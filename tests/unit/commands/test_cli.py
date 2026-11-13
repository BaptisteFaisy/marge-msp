"""The CLI contract: every command is discoverable and configurable.

A command whose ``configure`` hook is not attached silently loses its flags
(``marge generate --out`` was refused by argparse). These tests make that
impossible to ship again.
"""

from __future__ import annotations

import argparse
import importlib
import pkgutil

import pytest

import marge.commands as commands_pkg
from marge.cli import build_parser, discover_commands


def _modules() -> list[str]:
    return [module.name for module in pkgutil.iter_modules(commands_pkg.__path__)]


def test_every_command_module_declares_commands() -> None:
    for name in _modules():
        module = importlib.import_module(f"marge.commands.{name}")
        assert getattr(module, "COMMANDS", None), f"{name} exposes no COMMANDS"


def test_every_command_has_a_configure_hook() -> None:
    for name in _modules():
        module = importlib.import_module(f"marge.commands.{name}")
        for command, handler in module.COMMANDS.items():
            assert callable(handler), f"{name}.{command} is not callable"
            assert callable(getattr(handler, "configure", None)), (
                f"{name}.{command} has no configure hook: its flags would be refused"
            )


def test_discover_commands_finds_the_expected_set() -> None:
    found = set(discover_commands())
    assert {"smoke", "version", "demo", "generate", "eval", "load-demo"} <= found


def test_open_store_selects_the_backend(monkeypatch) -> None:
    """``load-demo`` writes to DynamoDB, the demo to SQLite: one switch."""
    from marge import store as store_pkg

    created: dict[str, str] = {}

    class FakeDynamo:
        def __init__(self, table_name, region_name=None):
            created["table"] = table_name
            created["region"] = region_name

    monkeypatch.setattr(store_pkg, "DynamoStore", FakeDynamo)
    opened = store_pkg.open_store(
        "unused.sqlite3", backend="dynamo", table_name="marge-validations", region_name="eu-west-1"
    )
    assert isinstance(opened, FakeDynamo)
    assert created == {"table": "marge-validations", "region": "eu-west-1"}
    assert isinstance(store_pkg.open_store("local.sqlite3"), store_pkg.SqliteStore)


def test_parser_accepts_the_flags_of_every_command() -> None:
    parser = build_parser()
    for command in discover_commands():
        with pytest.raises(SystemExit) as exit_info:
            parser.parse_args([command, "--help"])
        assert exit_info.value.code == 0


def test_smoke_command_passes() -> None:
    from marge.commands.core import smoke

    assert smoke(argparse.Namespace()) == 0


def test_version_command_prints_the_package_version(capsys) -> None:
    from marge.commands.core import version

    assert version(argparse.Namespace()) == 0
    assert capsys.readouterr().out.strip()
