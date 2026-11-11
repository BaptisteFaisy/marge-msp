"""Comparing classifiers on the same labelled set (idea 26).

One model is never chosen on a hunch: this module runs several named models on
the *same* labelled interventions (``data/generated/labels/interventions.jsonl``,
spec 13.3) and measures what the cahier des charges cares about:

* **agreement** with the labels, through :func:`classification_agreement` (R5);
* **false "out of scope"** on the interventions labelled ``clearly_included``,
  the hard R6 rule;
* **abstention rate** — the share of UNCERTAIN answers (spec 13.2 prudence);
* **average latency**, measured around each call;
* **number of calls**, the figure the AWS bill is made of.

A model is any object exposing ``complete(prompt, schema)`` and a ``model_id``
attribute, so the deterministic local model, a replayed recording and a real
Bedrock model all fit the same comparison. Everything here is offline and
deterministic; :class:`ReplayedModel` is how a Bedrock run recorded once is
compared again without credentials (the CI workers have none).
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from ..classify.output import parse_model_output
from ..classify.prompt import OUTPUT_SCHEMA, build_prompt
from ..domain import Classification, Contract, Intervention, WorkClass
from .classification_agreement import Label, classification_agreement, r6_violations
from .dataset import load
from .local_classifier import classify as local_classify
from .score import ZERO, Score, ratio


@dataclass(frozen=True, slots=True)
class ComparisonCase:
    """One labelled intervention, the contract in force, and the prompt to send."""

    intervention: Intervention
    contract: Contract
    label: Label
    prompt: str


def prompt_key(prompt: str) -> str:
    """Stable key of a prompt: same text, same key, on every machine."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


class ReplayedModel:
    """Replays recorded answers instead of calling a model (offline reference).

    Answers are keyed by :func:`prompt_key`, so a recording made on one machine
    is replayed identically anywhere. An unknown prompt yields ``default``
    (empty by default), which the parser rejects: a missing recording shows up
    as a failure rather than as a silent abstention.
    """

    def __init__(self, model_id: str, answers: Mapping[str, str], default: str = "") -> None:
        self.model_id = model_id
        self._answers = dict(answers)
        self._default = default

    def complete(self, prompt: str, schema: dict) -> str:
        return self._answers.get(prompt_key(prompt), self._default)

    def __len__(self) -> int:
        return len(self._answers)


def record_reference(cases: Sequence[ComparisonCase]) -> dict[str, str]:
    """Record the answers of the deterministic reference reader (spec 13.2).

    The eval-side rule reader is a different implementation from the keyword
    model of :mod:`marge.classify.bedrock`: comparing the two says whether the
    offline demo can stand in for a real model. Recording them once and
    replaying them is also the shape a recorded Bedrock run takes.
    """
    recorded: dict[str, str] = {}
    for case in cases:
        result = local_classify(case.intervention, case.contract)
        recorded[prompt_key(case.prompt)] = json.dumps(
            {
                "class": result.work_class.value,
                "confidence": float(result.confidence),
                "citedClause": result.cited_clause,
                "reason": result.reason,
            },
            ensure_ascii=False,
        )
    return recorded


def build_cases(root: Path | str, limit: int | None = None) -> list[ComparisonCase]:
    """The labelled interventions of a generated dataset, with their prompt."""
    dataset = load(Path(root))
    labels = {row["intervention_id"]: Label.from_dict(row) for row in dataset.labels}
    cases: list[ComparisonCase] = []
    for item in dataset.interventions:
        label = labels.get(item.intervention_id)
        if label is None:
            continue
        contract = dataset.contract_for(item.client_id or "", str(item.month))
        if contract is None:
            continue
        cases.append(ComparisonCase(item, contract, label, build_prompt(item, contract)))
    cases.sort(key=lambda case: case.intervention.intervention_id)
    return cases[:limit] if limit else cases


def _mean_ms(values: Sequence[float]) -> Decimal:
    """Average of measured durations, in milliseconds (two decimals)."""
    if not values:
        return ZERO
    total = sum((Decimal(str(value)) for value in values), ZERO)
    return ((total / Decimal(len(values))) * 1000).quantize(Decimal("0.01"))


@dataclass(frozen=True, slots=True)
class ModelStats:
    """One row of the comparison table."""

    model_id: str
    agreement: Score
    false_out_of_scope: int
    abstention_rate: Decimal
    mean_latency_ms: Decimal
    calls: int
    failures: int

    def as_dict(self) -> dict:
        return {
            "modelId": self.model_id,
            "agreement": self.agreement.as_dict(),
            "falseOutOfScope": self.false_out_of_scope,
            "abstentionRate": str(self.abstention_rate),
            "meanLatencyMs": str(self.mean_latency_ms),
            "calls": self.calls,
            "failures": self.failures,
        }


def _measure(model, cases: Sequence[ComparisonCase], clock: Callable[[], float]) -> ModelStats:
    """Run one model on every case and measure the five indicators."""
    predicted: list[Classification] = []
    latencies: list[float] = []
    calls = 0
    failures = 0
    for case in cases:
        calls += 1
        start = clock()
        try:
            raw = model.complete(case.prompt, OUTPUT_SCHEMA)
        except Exception:  # a broken model is a result of the comparison, not a crash
            failures += 1
            continue
        latencies.append(clock() - start)
        try:
            predicted.append(parse_model_output(raw, case.intervention, case.contract.version))
        except ValueError:  # InvalidModelOutput is a ValueError
            failures += 1
    labels = [case.label for case in cases]
    by_id = {item.intervention_id: item for item in predicted}
    abstentions = sum(1 for item in predicted if item.work_class == WorkClass.UNCERTAIN)
    return ModelStats(
        model_id=str(getattr(model, "model_id", "") or type(model).__name__),
        agreement=classification_agreement(predicted, labels),
        false_out_of_scope=len(r6_violations(by_id, labels)),
        abstention_rate=ratio(abstentions, len(predicted)),
        mean_latency_ms=_mean_ms(latencies),
        calls=calls,
        failures=failures,
    )


def compare_models(
    models: Sequence[object],
    cases: Sequence[ComparisonCase],
    clock: Callable[[], float] = time.perf_counter,
) -> list[ModelStats]:
    """Compare every model on the same cases, in the order they are given."""
    return [_measure(model, cases, clock) for model in models]


def render_table(stats: Sequence[ModelStats]) -> str:
    """The comparison table of idea 26, printable in a terminal."""
    lines = [
        f"{'model':<26} {'agreement':>10} {'R6 false-out':>13} {'abstention':>11}"
        f" {'latency ms':>11} {'calls':>6} {'failures':>9}",
        "-" * 92,
    ]
    for item in stats:
        lines.append(
            f"{item.model_id:<26} {item.agreement.percent:>9}% {item.false_out_of_scope:>13}"
            f" {item.abstention_rate * 100:>10.2f}% {item.mean_latency_ms:>11}"
            f" {item.calls:>6} {item.failures:>9}"
        )
    lines.append("-" * 92)
    lines.append("R5 target > 90.00% agreement, R6 target: 0 false out-of-scope on clearly included work")
    return "\n".join(lines)


def as_dict(stats: Sequence[ModelStats]) -> dict:
    """JSON-ready payload of the comparison (``marge model-compare --json``)."""
    return {
        "models": [item.as_dict() for item in stats],
        "targets": {"agreement": "0.90", "false_out_of_scope": 0},
    }


def to_json(stats: Sequence[ModelStats]) -> str:
    return json.dumps(as_dict(stats), indent=2, ensure_ascii=False)
