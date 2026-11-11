"""Persistence: one ``Store`` protocol, two backends (spec 15, ENF-REP-01)."""

from __future__ import annotations

from pathlib import Path

from .base import Store
from .sqlite_store import SqliteStore


def open_store(path: str | Path = "marge.sqlite3") -> SqliteStore:
    """Open (and migrate) the local SQLite store used by the demo and the CLI."""
    return SqliteStore(path)


__all__ = ["SqliteStore", "Store", "open_store"]
