"""Persistence: one ``Store`` protocol, two backends (spec 15, ENF-REP-01)."""

from __future__ import annotations

from pathlib import Path

from .athena import (
    ANALYTICAL_TABLE_NAMES,
    all_analytical_ddls,
    create_external_table_ddl,
    dataset_query,
    margin_recalculation_query,
)
from .base import Store
from .dynamo_store import DEFAULT_TABLE_NAME, DynamoStore, create_table_resources
from .sqlite_store import SqliteStore


def open_store(path: str | Path = "marge.sqlite3") -> SqliteStore:
    """Open (and migrate) the local SQLite store used by the demo and the CLI."""
    return SqliteStore(path)


__all__ = [
    "ANALYTICAL_TABLE_NAMES",
    "DEFAULT_TABLE_NAME",
    "DynamoStore",
    "SqliteStore",
    "Store",
    "all_analytical_ddls",
    "create_external_table_ddl",
    "create_table_resources",
    "dataset_query",
    "margin_recalculation_query",
    "open_store",
]
