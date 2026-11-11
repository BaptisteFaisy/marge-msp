"""Parquet writer for the analytical tables (idea 71).

Athena bills per byte scanned, so the same rows cost three to five times less in
compressed Parquet than in JSON Lines — and typed columns make the queries
faster too. Parquet needs a real writer, so ``pyarrow`` is imported inside the
function: the CI workers and the offline demo keep working on JSONL, and a
deployment that wants Parquet installs one extra package.

Column types are read from ``marge.store.athena.ANALYTICAL_TABLES`` — the same
source of truth as the DDL — so a table can never be written with one type and
declared with another.
"""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

from .tables import normalise_row, table_spec

COMPRESSION = "snappy"
EXTENSION = ".parquet"


class ParquetUnavailable(RuntimeError):
    """Raised when pyarrow is missing, with the fix in the message."""


def _pyarrow():
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on the host
        raise ParquetUnavailable(
            "parquet needs pyarrow: pip install pyarrow, or publish with --format jsonl"
        ) from exc
    return pa, pq


def _arrow_type(pa, sql_type: str):
    """Map one Athena column type onto its Arrow type."""
    upper = sql_type.upper()
    if upper.startswith("DECIMAL"):
        precision, _, scale = upper[len("DECIMAL(") :].rstrip(")").partition(",")
        return pa.decimal128(int(precision), int(scale or 0))
    if upper == "BOOLEAN":
        return pa.bool_()
    if upper == "INT" or upper == "INTEGER":
        return pa.int32()
    if upper == "BIGINT":
        return pa.int64()
    if upper == "DATE":
        return pa.date32()
    return pa.string()


def arrow_schema(name: str):
    """Arrow schema of one analytical table, derived from its DDL columns."""
    pa, _ = _pyarrow()
    spec = table_spec(name)
    fields = [pa.field(column.name, _arrow_type(pa, column.sql_type)) for column in spec.columns]
    fields += [pa.field(part.name, pa.string()) for part in spec.partition_keys]
    return pa.schema(fields)


def _typed(value: object):
    """Coerce one value to what Arrow expects, keeping amounts exact."""
    if value is None or isinstance(value, (str, bool, int, Decimal, date)):
        return value
    return str(value)


def to_parquet(name: str, rows: list[dict]) -> bytes:
    """Serialize rows of one analytical table into a Snappy Parquet buffer."""
    pa, pq = _pyarrow()
    schema = arrow_schema(name)
    names = [field.name for field in schema]
    typed_rows = (normalise_row(name, row) for row in rows)
    payload = [{key: _typed(row.get(key)) for key in names} for row in typed_rows]
    table = (
        pa.Table.from_pylist(payload, schema=schema)
        if payload
        else pa.table({name_: [] for name_ in names}, schema=schema)
    )
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression=COMPRESSION)
    return buffer.getvalue()


def read_parquet(payload: bytes) -> list[dict]:
    """Read a Parquet buffer back — used by the round-trip test."""
    _, pq = _pyarrow()
    table = pq.read_table(io.BytesIO(payload))
    return table.to_pylist()
