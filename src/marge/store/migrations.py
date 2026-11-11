"""Schema migrations, applied in lexical order (EF-CAL-03, spec 15).

Each migration is an immutable SQL file under ``store/migrations/``. The
applied version is recorded in ``schema_version`` so a second start is a
no-op.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def available_migrations(directory: Path | None = None) -> list[Path]:
    """Every ``*.sql`` migration, in lexical order."""
    root = directory or MIGRATIONS_DIR
    return sorted(root.glob("*.sql"))


MIGRATIONS = available_migrations()


def current_version(conn: sqlite3.Connection) -> int:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    return int(row["v"] or 0) if row and row["v"] is not None else 0


def apply_migrations(conn: sqlite3.Connection, directory: Path | None = None) -> int:
    """Apply every pending migration and return the resulting version."""
    done = current_version(conn)
    applied = done
    for index, path in enumerate(available_migrations(directory), start=1):
        if index <= done:
            continue
        conn.executescript(path.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (index,))
        conn.commit()
        applied = index
    return applied
