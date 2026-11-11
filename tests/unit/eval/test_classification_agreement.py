"""Classification agreement (R5) and the hard R6 rule (spec 13.2/13.3)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from marge.domain import Classification, Intervention, WorkClass, WorkLevel
from marge.eval.classification_agreement import (
    Label,
    classification_agreement,
)


def _intervention(intervention_id: str, text: str, hours: str = "2.00") -> Intervention:
    return Intervention(
        intervention_id=intervention_id,
        ticket_id=f"t-{intervention_id}",
        client_id="c-001",
        occurred_on=date(2026, 10, 5),
        category=text,
        level=WorkLevel.N2,
        hours_spent=Decimal(hours),
        description=text,
    )


def _classification(intervention_id: str, work_class: WorkClass) -> Classification:
    return Classification(
        intervention_id=intervention_id,
        client_id="c-001",
        contract_version=1,
        work_class=work_class,
        confidence=Decimal("0.9"),
    )


def _label(intervention_id: str, work_class: WorkClass, clearly: bool = False) -> Label:
    return Label(intervention_id=intervention_id, expected_class=work_class, clearly_included=clearly)


def test_label_from_dict_reads_the_jsonl_shape():
    label = Label.from_dict(
        {"intervention_id": "wl-000001", "expected_class": "OUT_OF_SCOPE", "clearly_included": False}
    )
    assert label.expected_class == WorkClass.OUT_OF_SCOPE
    assert label.clearly_included is False


def test_classification_agreement_is_one_when_every_class_matches():
    labels = [_label("wl-1", WorkClass.INCLUDED), _label("wl-2", WorkClass.OUT_OF_SCOPE)]
    predicted = [
        _classification("wl-1", WorkClass.INCLUDED),
        _classification("wl-2", WorkClass.OUT_OF_SCOPE),
    ]
    score = classification_agreement(predicted, labels)
    assert score.value == Decimal("1")
    assert score.passed is True


def test_classification_agreement_counts_a_miss():
    labels = [_label("wl-1", WorkClass.INCLUDED), _label("wl-2", WorkClass.INCLUDED)]
    predicted = [
        _classification("wl-1", WorkClass.INCLUDED),
        _classification("wl-2", WorkClass.UNCERTAIN),
    ]
    score = classification_agreement(predicted, labels)
    assert score.value == Decimal("0.5000")
    assert score.passed is False


def test_classification_agreement_fails_on_one_r6_violation():
    """A clearly included intervention classified OUT_OF_SCOPE fails everything."""
    labels = [_label(f"wl-{index}", WorkClass.INCLUDED, clearly=True) for index in range(10)]
    predicted = [_classification(f"wl-{index}", WorkClass.INCLUDED) for index in range(9)]
    predicted.append(_classification("wl-9", WorkClass.OUT_OF_SCOPE))
    score = classification_agreement(predicted, labels)
    assert score.value == Decimal("0.9000")
    assert score.passed is False
    assert any("R6 violation" in line for line in score.detail)


def test_classification_agreement_allows_uncertain_on_clearly_included_work():
    """R6 only forbids OUT_OF_SCOPE; the prudence rule makes UNCERTAIN legitimate."""
    labels = [_label("wl-1", WorkClass.INCLUDED, clearly=True)]
    score = classification_agreement([_classification("wl-1", WorkClass.UNCERTAIN)], labels)
    assert not any("R6 violation" in line for line in score.detail)


def test_classification_agreement_ignores_unlabelled_predictions():
    labels = [_label("wl-1", WorkClass.INCLUDED)]
    predicted = [
        _classification("wl-1", WorkClass.INCLUDED),
        _classification("wl-999", WorkClass.OUT_OF_SCOPE),
    ]
    score = classification_agreement(predicted, labels)
    assert score.value == Decimal("1")
    assert score.passed is True


def test_classification_agreement_reports_per_class_counts():
    labels = [
        _label("wl-1", WorkClass.INCLUDED),
        _label("wl-2", WorkClass.OUT_OF_SCOPE),
        _label("wl-3", WorkClass.UNCERTAIN),
    ]
    predicted = [
        _classification("wl-1", WorkClass.INCLUDED),
        _classification("wl-2", WorkClass.INCLUDED),
        _classification("wl-3", WorkClass.UNCERTAIN),
    ]
    detail = " ".join(classification_agreement(predicted, labels).detail)
    assert "IN_SCOPE 1/1" in detail
    assert "OUT_OF_SCOPE 0/1" in detail
    assert "UNCERTAIN 1/1" in detail


@pytest.mark.parametrize("work_class", [WorkClass.INCLUDED, WorkClass.OUT_OF_SCOPE])
def test_classification_agreement_handles_a_single_label(work_class):
    score = classification_agreement([_classification("wl-1", work_class)], [_label("wl-1", work_class)])
    assert score.value == Decimal("1")
