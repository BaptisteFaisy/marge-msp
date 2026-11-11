"""``marge model-compare`` — compare classifiers on the labelled set (idea 26).

Offline by default: the deterministic keyword model of
:mod:`marge.classify.bedrock` against a **replayed** reference model — the
answers of the eval-side rule reader, recorded once and replayed through the
model interface. Pass ``--bedrock`` to put a real Bedrock model in the
comparison; boto3 is imported inside that branch only, so the offline path
never needs the AWS SDK (docs/CONTRACT.md rule 4).
"""

from __future__ import annotations

import argparse
from pathlib import Path

LOCAL_MODEL = "local"
SCRIPTED_MODEL = "scripted"
BEDROCK_MODEL = "bedrock"
OFFLINE_MODELS = (LOCAL_MODEL, SCRIPTED_MODEL)
REFERENCE_NAMES = (SCRIPTED_MODEL, "reference")


def _local_model():
    """The deterministic keyword model shipped with the classifier."""
    from marge.classify.bedrock import LocalRuleModel

    return LocalRuleModel()


def _replayed_model(cases):
    """The reference reader, recorded once and replayed through the interface."""
    from marge.eval.model_comparison import ReplayedModel, record_reference

    return ReplayedModel("replayed-reference", record_reference(cases))


def _bedrock_model(model_id: str):
    """A real Bedrock model. boto3 is imported here, never at module level."""
    import boto3  # noqa: F401 - the offline path must never import the AWS SDK

    from marge.classify.bedrock import BedrockClassifierModel

    return BedrockClassifierModel(model_id=model_id)


def _build_models(args: argparse.Namespace, cases) -> list:
    """Instantiate the models asked for, in the order of ``--models``."""
    models = []
    for name in (item.strip().lower() for item in args.models.split(",")):
        if not name:
            continue
        if name == LOCAL_MODEL:
            models.append(_local_model())
        elif name in REFERENCE_NAMES:
            models.append(_bedrock_model(args.model_id) if args.bedrock else _replayed_model(cases))
        elif name == BEDROCK_MODEL:
            if not args.bedrock:
                raise ValueError(f"{BEDROCK_MODEL!r} needs --bedrock (it calls AWS)")
            models.append(_bedrock_model(args.model_id))
        else:
            raise ValueError(f"unknown model {name!r}: choose from local, scripted, bedrock")
    if not models:
        raise ValueError("no model to compare")
    return models


def model_compare(args: argparse.Namespace) -> int:
    """Compare the named models on the labelled set and print the table."""
    from marge.eval.model_comparison import build_cases, compare_models, render_table, to_json

    try:
        cases = build_cases(Path(args.data), limit=args.limit)
    except FileNotFoundError:
        cases = []
    if not cases:
        print(f"MODEL COMPARE FAILED — no labelled intervention under {args.data}")
        return 1
    try:
        models = _build_models(args, cases)
    except ValueError as exc:
        print(f"MODEL COMPARE FAILED — {exc}")
        return 1
    stats = compare_models(models, cases)
    if args.json:
        print(to_json(stats))
        return 0
    print(render_table(stats))
    print(f"\n{len(cases)} labelled intervention(s) of {args.data}")
    return 0


def configure(parser: argparse.ArgumentParser) -> None:
    from marge.classify.bedrock import DEFAULT_MODEL_ID

    parser.add_argument("--data", default="data/generated", help="dataset directory (marge generate)")
    parser.add_argument(
        "--models",
        default=",".join(OFFLINE_MODELS),
        help="comma separated model names: local, scripted, bedrock",
    )
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID, help="Bedrock model or profile id")
    parser.add_argument("--limit", type=int, default=0, help="compare on the first N labels only")
    parser.add_argument(
        "--bedrock",
        action="store_true",
        help="call the real Bedrock model instead of the replayed reference",
    )
    parser.add_argument("--json", action="store_true", help="print the comparison as JSON")


model_compare.configure = configure  # type: ignore[attr-defined]

COMMANDS = {"model-compare": model_compare}
