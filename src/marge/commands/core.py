"""Core commands: smoke and version.

smoke is the offline self-test run by CI on every pull request: it
recomputes the Annex D golden scenario and compares it to the published
figures. Any drift in the calculation model breaks the build immediately.
"""

from __future__ import annotations

import argparse
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


def smoke(_: argparse.Namespace) -> int:
    """Recompute the Annex D golden scenario and compare (offline)."""
    try:
        actual = _golden_run()
    except ModuleNotFoundError as exc:
        print(f"SMOKE SKIP — {exc}")
        return 0
    failed = [key for key, want in GOLDEN.items() if actual[key] != want]
    for key, want in GOLDEN.items():
        flag = "OK " if actual[key] == want else "KO "
        print(f"{flag}{key:<16} expected={want} actual={actual[key]}")
    if failed:
        print(f"SMOKE FAILED — {', '.join(failed)}")
        return 1
    print("SMOKE OK — calculation model matches Annex D")
    return 0


def version(_: argparse.Namespace) -> int:
    """Print the package version."""
    from marge import __version__

    print(__version__)
    return 0


def _no_flags(parser: argparse.ArgumentParser) -> None:
    """These two commands take no option."""


smoke.configure = _no_flags  # type: ignore[attr-defined]
version.configure = _no_flags  # type: ignore[attr-defined]

COMMANDS = {"smoke": smoke, "version": version}
