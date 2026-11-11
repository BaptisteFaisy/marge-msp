"""The Quick asset bundle (docs/CONTRACT.md, ``marge.quicksight.to_asset_bundle``).

One deterministic JSON document holding the datasets, the topic, the
dashboards, the row-level rules, the scenarios, the agent instructions and the
flows. It is written under ``infra/quicksight-assets/`` and replayed by
``marge.quicksight.deploy``.

The bundle is deterministic: no timestamp, no random identifier. Two calls to
:func:`to_asset_bundle` return the same JSON.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .agent import AGENT
from .dashboards import DASHBOARDS
from .datasets import DATASETS
from .flows import FLOWS
from .models import to_jsonable
from .rls import RLS_RULES
from .scenarios import SCENARIOS
from .topic import TOPIC

__all__ = [
    "ACCOUNT_NAME",
    "BUNDLE_VERSION",
    "DEFAULT_REGION",
    "bundle_json",
    "to_asset_bundle",
    "write_bundle",
]

BUNDLE_VERSION = "1.0.0"
"""Version of the bundle format, bumped when the shape changes."""

BUNDLE_NAME = "marge-assets.json"
"""Name of the bundle file written under ``infra/quicksight-assets/``."""

ACCOUNT_NAME = "marge-hackathon"
"""Name of the Quick account that hosts the assets."""

DEFAULT_REGION = "eu-west-3"
"""Region of the deployment, Paris (settings.region of the domain layer)."""


def to_asset_bundle() -> dict[str, Any]:
    """Build the full asset bundle as plain JSON-ready Python objects."""
    return {
        "bundle_version": BUNDLE_VERSION,
        "generated_by": "marge.quicksight.assets.to_asset_bundle",
        "account": {
            "name": ACCOUNT_NAME,
            "region": DEFAULT_REGION,
            "language": "en",
        },
        "datasets": to_jsonable(DATASETS),
        "topic": to_jsonable(TOPIC),
        "dashboards": to_jsonable(DASHBOARDS),
        "rls_rules": to_jsonable(RLS_RULES),
        "scenarios": to_jsonable(SCENARIOS),
        "agent": to_jsonable(AGENT),
        "flows": to_jsonable(FLOWS),
    }


def bundle_json(indent: int = 2) -> str:
    """Serialise the bundle to JSON, deterministically."""
    return json.dumps(to_asset_bundle(), indent=indent, sort_keys=True, ensure_ascii=False) + "\n"


def write_bundle(directory: str | Path, indent: int = 2) -> Path:
    """Write the bundle as ``marge-assets.json`` in ``directory``."""
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    path = target / BUNDLE_NAME
    path.write_text(bundle_json(indent=indent), encoding="utf-8")
    return path


def check_bundle(directory: str | Path) -> bool:
    """Tell whether the committed bundle is the one the code produces.

    Used by the deployment check: a stale bundle means the Quick assets and
    the code have drifted apart.
    """
    path = Path(directory) / BUNDLE_NAME
    if not path.exists():
        return False
    return path.read_text(encoding="utf-8") == bundle_json()


def main(argv: list[str] | None = None) -> int:
    """Entry point: ``python -m marge.quicksight.assets --out infra/quicksight-assets``."""
    parser = argparse.ArgumentParser(description="Write the Marge Quick asset bundle")
    parser.add_argument(
        "--out",
        default="infra/quicksight-assets",
        help="directory where the bundle is written",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="only check that the committed bundle is up to date",
    )
    args = parser.parse_args(argv)
    if args.check:
        if not check_bundle(args.out):
            print(f"BUNDLE STALE {args.out}/{BUNDLE_NAME}")
            return 1
        print(f"BUNDLE OK {args.out}/{BUNDLE_NAME}")
        return 0
    path = write_bundle(args.out)
    print(f"BUNDLE {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
