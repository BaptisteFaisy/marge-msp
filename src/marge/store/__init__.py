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


def open_store(
    path: str | Path = "marge.sqlite3",
    *,
    backend: str = "sqlite",
    table_name: str = "",
    region_name: str = "",
) -> SqliteStore | DynamoStore:
    """Open the store of the requested backend.

    ``sqlite`` is the local one: the demo, the tests, the CI. ``dynamo`` is
    the deployed one: the same ``Store`` protocol, the same data, the same
    code — only the persistence differs (ENF-REP-01).

    ``boto3`` stays lazily imported by ``DynamoStore``, so a local run never
    needs it (CONTRACT rule 4).
    """
    if backend == "dynamo":
        return DynamoStore(table_name or DEFAULT_TABLE_NAME, region_name=region_name or None)
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
