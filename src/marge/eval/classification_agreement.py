"""Classification agreement (spec 13.3, R5/R6): > 90 %, and no false "out".

R6 is a hard rule: an intervention marked ``clearly_included`` in the labelled
set must **never** come back as ``OUT_OF_SCOPE``. One violation fails the whole
measure, whatever the agreement ratio is (spec 13.2 prudence rule).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from ..domain import Classification, WorkClass
from .score import Score, score_of

TARGET = Decimal("0.90")


@dataclass(frozen=True, slots=True)
class Label:
    """One line of ``labels/interventions.jsonl`` (ground truth)."""

    intervention_id: str
    expected_class: WorkClass
    clearly_included: bool = False

    @classmethod
    def from_dict(cls, row: dict) -> Label:
        return cls(
            intervention_id=str(row["intervention_id"]),
            expected_class=WorkClass(row["expected_class"]),
            clearly_included=bool(row.get("clearly_included", False)),
        )


def _violations(predicted: dict[str, Classification], labels: Sequence[Label]) -> list[Label]:
    """Labelled interventions that are clearly included yet called out of scope."""
    return [
        label
        for label in labels
        if label.clearly_included
        and label.intervention_id in predicted
        and predicted[label.intervention_id].work_class == WorkClass.OUT_OF_SCOPE
    ]


def _class_tally(
    predicted: dict[str, Classification], labels: Sequence[Label]
) -> tuple[int, dict[WorkClass, list[int]]]:
    """Count hits and per-class ``[hits, total]``."""
    tally: dict[WorkClass, list[int]] = {work_class: [0, 0] for work_class in WorkClass}
    hits = 0
    for label in labels:
        tally[label.expected_class][1] += 1
        found = predicted.get(label.intervention_id)
        if found is not None and found.work_class == label.expected_class:
            hits += 1
            tally[label.expected_class][0] += 1
    return hits, tally


def classification_agreement(predicted: Sequence[Classification], labels: Sequence[Label]) -> Score:
    """Agreement between the classifier output and the labelled set (R5/R6)."""
    by_id = {item.intervention_id: item for item in predicted}
    hits, tally = _class_tally(by_id, labels)
    violations = _violations(by_id, labels)
    detail = [
        f"{len(labels)} labelled intervention(s), {len(predicted)} classification(s)",
        "per class: "
        + ", ".join(f"{work_class.value} {values[0]}/{values[1]}" for work_class, values in tally.items()),
    ]
    for label in violations[:5]:
        detail.append(f"R6 violation: {label.intervention_id} is clearly included but OUT_OF_SCOPE")
    if len(violations) > 5:
        detail.append(f"... and {len(violations) - 5} more R6 violation(s)")
    return score_of(hits, len(labels), TARGET, detail, forced_failure=bool(violations))
