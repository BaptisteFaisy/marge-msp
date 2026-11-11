"""``marge eval`` — measure the four AI steps (spec 13.3, R2, R3, R5, R11)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def evaluate(args: argparse.Namespace) -> int:
    """Run the accuracy harnesses on the generated dataset and print the scores."""
    from marge.eval.harness import run_all

    report = run_all(Path(args.data))
    if args.json:
        payload = {
            name: {"value": str(score.value), "target": str(score.target), "passed": score.passed}
            for name, score in report.scores.items()
        }
        payload["stats"] = {key: str(value) for key, value in report.stats.items()}
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    failed = []
    for name, score in report.scores.items():
        flag = "OK " if score.passed else "KO "
        print(f"{flag}{name:<30} {score.percent} % (target {score.target})")
        if not score.passed:
            failed.append(name)
    print("EVAL OK" if not failed else f"EVAL FAILED — {', '.join(failed)}")
    return 0 if not failed else 1


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data", default="data/generated", help="dataset directory")
    parser.add_argument("--json", action="store_true", help="print the raw report")


evaluate.configure = configure  # type: ignore[attr-defined]

COMMANDS = {"eval": evaluate}
