"""``marge publish`` — write the analytical tables to the lake (Annex A)."""

from __future__ import annotations

import argparse

from ..domain import Month


def _months(raw: str) -> list[Month] | None:
    if not raw:
        return None
    return [Month.parse(part.strip()) for part in raw.split(",") if part.strip()]


def publish(args: argparse.Namespace) -> int:
    """Publish the five analytical tables, locally or to the curated S3 bucket."""
    from ..publish import LocalWriter, S3Writer
    from ..publish import publish as run_publish
    from ..store import open_store

    store = open_store(args.db)
    writer = S3Writer(args.s3) if args.s3 else LocalWriter(args.out)
    report = run_publish(
        store,
        writer,
        months=_months(args.month),
        prefix=args.prefix,
        database=args.database,
        bucket=args.s3 or "",
        file_format=args.format,
    )

    for table in report.tables:
        print(f"{table.table:<32} {table.rows:>6} ligne(s) -> {len(table.keys)} fichier(s)")
        for uri in table.uris[:2]:
            print(f"    {uri}")
    print(f"total : {report.rows} lignes, {report.files} fichiers")

    if args.ddl:
        print()
        for name, ddl in report.ddls.items():
            print(f"-- {name}")
            print(ddl)
            print()
    return 0


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", default="marge.sqlite3", help="sqlite store to read")
    parser.add_argument("--out", default="data/published", help="local root (ignored with --s3)")
    parser.add_argument("--s3", default="", help="curated bucket name (enables the S3 writer)")
    parser.add_argument("--prefix", default="analytical", help="prefix inside the bucket or root")
    parser.add_argument("--database", default="marge", help="Glue database name")
    parser.add_argument("--month", default="", help="comma separated YYYY-MM list (default: all)")
    parser.add_argument("--ddl", action="store_true", help="also print the Athena DDL")
    parser.add_argument(
        "--format",
        default="jsonl",
        choices=("jsonl", "parquet"),
        help="jsonl needs no dependency, parquet is 3-5x cheaper to query (needs pyarrow)",
    )


publish.configure = configure  # type: ignore[attr-defined]

COMMANDS = {"publish": publish}
