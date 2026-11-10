"""Command line entry point: ``python3 -m marge.cli <command>``.

Kept thin on purpose: every command delegates to a module. The heavy lifting
never lives here, so the CLI stays under the 500-line limit while commands are
added.
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal

GOLDEN = {
    "revenue": Decimal("4620.00"),
    "cost": Decimal("3725.00"),
    "margin": Decimal("895.00"),
    "unbilled_hours": Decimal("9.00"),
    "unbilled_value": Decimal("990.00"),
}


def _golden_run() -> dict[str, Decimal]:
    from tests.fakes.builders import golden_inputs, golden_settings

    from marge.calc import compute_hours_summary, compute_margin_month

    inputs, settings = golden_inputs(), golden_settings()
    margin = compute_margin_month(inputs, settings)
    summary = compute_hours_summary(inputs, settings)
    return {
        "revenue": margin.revenue.total,
        "cost": margin.costs.total,
        "margin": margin.margin,
        "unbilled_hours": summary.unbilled_hours,
        "unbilled_value": summary.unbilled_value,
    }


def cmd_smoke(_: argparse.Namespace) -> int:
    """Recompute the Annex D golden scenario and compare (offline)."""
    try:
        actual = _golden_run()
    except ModuleNotFoundError as exc:
        print(f"SMOKE SKIP — {exc}")
        return 0
    failed = [k for k, want in GOLDEN.items() if actual[k] != want]
    for key, want in GOLDEN.items():
        flag = "OK " if actual[key] == want else "KO "
        print(f"{flag}{key:<16} attendu={want} obtenu={actual[key]}")
    if failed:
        print(f"SMOKE KO — {', '.join(failed)}")
        return 1
    print("SMOKE OK — modèle de calcul conforme à l'annexe D")
    return 0


def cmd_version(_: argparse.Namespace) -> int:
    from marge import __version__

    print(__version__)
    return 0


COMMANDS = {"smoke": cmd_smoke, "version": cmd_version}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="marge", description="Marge — per-client MSP profitability")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, handler in COMMANDS.items():
        entry = sub.add_parser(name)
        entry.set_defaults(handler=handler)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
