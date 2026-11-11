"""``marge generate`` — build the demo MSP dataset (spec 19.1)."""

from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_OUT = Path("data/generated")


def generate(args: argparse.Namespace) -> int:
    """Generate the fictional MSP dataset (12 clients, 6 months, 12 contracts)."""
    from data.generator.build import generate

    out = Path(args.out)
    manifest = generate(out)
    print(f"dataset written to {out}")
    for key, value in sorted(manifest.items()):
        print(f"  {key}: {value}")
    return 0


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="output directory")
    parser.add_argument(
        "--seed",
        type=int,
        default=20261111,
        help="the generator seed is fixed in data/generator/common.py",
    )


generate.configure = configure  # type: ignore[attr-defined]

COMMANDS = {"generate": generate}
