"""``marge load-demo`` — load the demonstration dataset into a store.

One replayable command: the demonstration environment is rebuilt from the
generator, with the same seed, whatever the state of the table is. Every row
is written on its natural key, so running it twice leaves the same result.

The command is the deployed path (spec 8.1, spec 19): the three sources are
loaded, the client matches are *proposed* and left for the controller to
validate, the contracts are read and validated but one — the seeded one — is
left in ``EXTRACTED`` so that its margin shows ``INCOMPLETE`` (R4), and the
work is classified so the account manager has an out-of-scope queue to clear
(EF-CLS-03).

Nothing is invented: the dataset comes from ``data/generator`` and every
figure is computed by ``marge.calc`` (ENF-IA-01).
"""

from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_TABLE = "marge-validations"
DEFAULT_REGION = "eu-west-1"
SEEDED_UNVALIDATED = "ctr-010"
"""The contract the generator leaves for the controller (R4)."""


def _months(args) -> list:
    from ..domain import Month
    from ..ingest import SourceFiles

    if args.month:
        return [Month.parse(part.strip()) for part in args.month.split(",") if part.strip()]
    from .demo import _months_in

    return _months_in(SourceFiles.of(Path(args.data)))


def _model(name: str):
    """The classifier model: the deterministic local rules, or Bedrock."""
    if name == "bedrock":
        from ..classify.bedrock import BedrockClassifierModel

        return BedrockClassifierModel()
    from ..classify import LocalRuleModel

    return LocalRuleModel()


def load_demo(args: argparse.Namespace) -> int:
    """Load the demonstration dataset and report what was written."""
    from ..ingest import SourceFiles
    from ..store import open_store
    from .demo import _classifier, run_pipeline

    root = Path(args.data)
    if not (root / "clients.json").exists():
        from data.generator.build import generate

        print(f"no dataset in {root}: generating one…")
        generate(root)

    store = open_store(
        args.db,
        backend=args.backend,
        table_name=args.table,
        region_name=args.region,
    )
    files = SourceFiles.of(root)
    months = _months(args)
    keep = {part.strip() for part in args.keep_unvalidated.split(",") if part.strip()}

    counts = run_pipeline(
        store,
        files,
        months,
        approve_matches=args.approve_matches,
        read_contracts=True,
        keep_unvalidated=keep,
        classifier=_classifier(store, _model(args.model)),
    )

    print(f"backend:  {args.backend}")
    print(f"months:   {', '.join(str(m) for m in months)}")
    for key in sorted(counts):
        print(f"{key + ':':<20} {counts[key]}")

    if args.publish_s3:
        _publish(store, args.publish_s3, args.publish_prefix)
    return 0


def _publish(store, bucket: str, prefix: str) -> None:
    """Publish the five analytical tables to the curated bucket (Annex A)."""
    from ..publish import S3Writer
    from ..publish import publish as run_publish

    report = run_publish(store, S3Writer(bucket), prefix=prefix, database="marge", bucket=bucket)
    print(f"published: {report.rows} rows, {report.files} files -> s3://{bucket}/{prefix}/")


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data", default="data/generated", help="dataset directory")
    parser.add_argument(
        "--backend",
        default="dynamo",
        choices=("dynamo", "sqlite"),
        help="deployed store (dynamo) or local one (sqlite)",
    )
    parser.add_argument("--db", default="marge.sqlite3", help="sqlite file (backend=sqlite)")
    parser.add_argument("--table", default=DEFAULT_TABLE, help="DynamoDB table (backend=dynamo)")
    parser.add_argument("--region", default=DEFAULT_REGION, help="AWS region (backend=dynamo)")
    parser.add_argument(
        "--model",
        default="local",
        choices=("local", "bedrock"),
        help="classifier: deterministic local rules, or a real Bedrock model",
    )
    parser.add_argument("--month", default="", help="comma separated YYYY-MM list (default: all)")
    parser.add_argument(
        "--keep-unvalidated",
        default=SEEDED_UNVALIDATED,
        help="comma separated contract ids left EXTRACTED for the controller",
    )
    parser.add_argument(
        "--approve-matches",
        action="store_true",
        help="approve the client matches instead of leaving them for the controller",
    )
    parser.add_argument("--publish-s3", default="", help="curated bucket to publish the tables to")
    parser.add_argument("--publish-prefix", default="analytical", help="prefix in the curated bucket")


load_demo.configure = configure  # type: ignore[attr-defined]

COMMANDS = {"load-demo": load_demo}
