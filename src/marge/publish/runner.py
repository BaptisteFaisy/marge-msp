"""Publishing the five analytical tables so Athena and Quick can read them.

This is the missing link between the Python calculation and the dashboards:
the store holds the figures, the lake holds files. The layout is the one Athena
expects for a partitioned external table, so ``MSCK REPAIR TABLE`` (or a
partition projection) picks the new months up without a schema change.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain import Month
from ..store.athena import ANALYTICAL_TABLES, all_analytical_ddls
from ..store.base import Store
from .tables import columns_of, render_jsonl, rows_of
from .writers import Writer

FILE_FORMATS = {"jsonl": ("JSONL", ".jsonl"), "parquet": ("PARQUET", ".parquet")}
DEFAULT_FORMAT = "jsonl"
# Nom conservé pour les appelants qui lisaient l'ancien format unique.
FILE_FORMAT = "JSONL"


@dataclass(slots=True)
class TablePublication:
    """What was written for one analytical table."""

    table: str
    rows: int
    keys: list[str] = field(default_factory=list)
    uris: list[str] = field(default_factory=list)

    @property
    def partitioned(self) -> bool:
        return "month" in columns_of(self.table)


@dataclass(slots=True)
class PublishReport:
    """Outcome of one publication run."""

    prefix: str
    tables: list[TablePublication] = field(default_factory=list)
    ddls: dict[str, str] = field(default_factory=dict)

    @property
    def rows(self) -> int:
        return sum(t.rows for t in self.tables)

    @property
    def files(self) -> int:
        return sum(len(t.keys) for t in self.tables)


def months_of(store: Store, months: list[Month] | None) -> list[Month]:
    """The months to publish: the requested ones, or every month with data."""
    if months:
        return sorted(months)
    return sorted({row.month for row in store.list_margin_months()})


def _keys_for(table: str, prefix: str, months: list[Month], partitioned: bool, ext: str) -> list[str]:
    if not partitioned:
        return [f"{prefix}/{table}/part-0{ext}"]
    return [f"{prefix}/{table}/month={month}/part-0{ext}" for month in months]


def _month_of_key(key: str) -> str:
    """``analytical/t/month=2026-10/part-0.jsonl`` -> ``2026-10``."""
    marker = "month="
    start = key.index(marker) + len(marker)
    return key[start:].split("/")[0]


def _render(table: str, rows: list[dict], file_format: str) -> bytes:
    """Encode one partition in the requested format."""
    if file_format == "parquet":
        from .parquet import to_parquet

        return to_parquet(table, rows)
    return render_jsonl(table, rows).encode("utf-8")


def _payloads(
    table: str, rows: list[dict], keys: list[str], partitioned: bool, file_format: str
) -> list[tuple[str, bytes]]:
    """One payload per key: partitioned tables are split by month."""
    if not partitioned:
        return [(keys[0], _render(table, rows, file_format))]
    payloads: list[tuple[str, bytes]] = []
    for key in keys:
        month = _month_of_key(key)
        subset = [row for row in rows if str(row.get("month")) == month]
        payloads.append((key, _render(table, subset, file_format)))
    return payloads


def publish(
    store: Store,
    writer: Writer,
    *,
    months: list[Month] | None = None,
    prefix: str = "analytical",
    database: str = "marge",
    bucket: str = "",
    file_format: str = DEFAULT_FORMAT,
) -> PublishReport:
    """Write every Annex A table through ``writer`` and return the report.

    ``file_format`` is ``jsonl`` (standard library, the default) or ``parquet``
    (needs pyarrow, three to five times cheaper to query in Athena). The DDL
    returned in the report always matches the format actually written.
    """
    chosen = file_format.lower()
    if chosen not in FILE_FORMATS:
        raise ValueError(f"unknown format {file_format!r}: use jsonl or parquet")
    ddl_format, extension = FILE_FORMATS[chosen]
    targets = months_of(store, months)
    report = PublishReport(prefix=prefix.strip("/"))

    for spec in ANALYTICAL_TABLES:
        rows = rows_of(spec.name, store, targets)
        partitioned = bool(spec.partition_keys)
        keys = _keys_for(spec.name, report.prefix, targets, partitioned, extension)
        publication = TablePublication(table=spec.name, rows=len(rows))
        for key, payload in _payloads(spec.name, rows, keys, partitioned, chosen):
            publication.keys.append(key)
            publication.uris.append(writer.write(key, payload))
        report.tables.append(publication)

    report.ddls = all_analytical_ddls(
        database=database,
        bucket=bucket or "local",
        prefix=report.prefix,
        file_format=ddl_format,
    )
    return report
