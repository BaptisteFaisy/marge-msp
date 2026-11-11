"""Persistence: one ``Store`` protocol, two backends (spec 15, ENF-REP-01)."""

from __future__ import annotations

from .base import Store
from .sqlite_store import SqliteStore

__all__ = ["SqliteStore", "Store"]
