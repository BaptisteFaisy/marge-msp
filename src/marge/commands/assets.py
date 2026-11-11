"""``marge assets`` — write and check the Quick asset bundle (spec 7, ENF-REP-01)."""

from __future__ import annotations

import argparse

DEFAULT_OUT = "infra/quicksight-assets"


def assets(args: argparse.Namespace) -> int:
    """Write the Quick asset bundle, or verify the committed one."""
    from marge.quicksight import bundle_json
    from marge.quicksight.assets import check_bundle, write_bundle

    if args.check:
        ok = check_bundle(args.out)
        print(f"asset bundle {'matches' if ok else 'DIFFERS from'} {args.out}")
        return 0 if ok else 1
    if args.stdout:
        print(bundle_json())
        return 0
    path = write_bundle(args.out)
    print(f"asset bundle written to {path}")
    return 0


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out", default=DEFAULT_OUT, help="bundle directory")
    parser.add_argument("--check", action="store_true", help="verify without writing")
    parser.add_argument("--stdout", action="store_true", help="print the bundle and exit")


assets.configure = configure  # type: ignore[attr-defined]

COMMANDS = {"assets": assets}
