"""``Score`` and its helpers: the shape every harness returns (spec 13.3)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from marge.eval.score import Score, format_report, ratio, score_of


def test_score_percent_formats_the_value():
    score = Score(value=Decimal("0.9143"), target=Decimal("0.90"), passed=True)
    assert score.percent == Decimal("91.43")


def test_score_gap_is_signed_against_the_target():
    assert Score(Decimal("0.5"), Decimal("0.9"), False).gap == Decimal("-0.4000")
    assert Score(Decimal("0.95"), Decimal("0.9"), True).gap == Decimal("0.0500")


def test_score_as_dict_keeps_decimals_as_strings():
    payload = Score(Decimal("1"), Decimal("0.9"), True, ["ok"]).as_dict()
    assert payload["value"] == "1"
    assert payload["percent"] == "100.00"
    assert payload["passed"] is True
    assert payload["detail"] == ["ok"]


def test_ratio_returns_zero_on_an_empty_denominator():
    assert ratio(0, 0) == Decimal("0")
    assert ratio(3, 4) == Decimal("0.7500")


def test_score_of_passes_only_above_the_target():
    assert score_of(91, 100, Decimal("0.90")).passed is True
    assert score_of(90, 100, Decimal("0.90")).passed is False


def test_score_of_forced_failure_overrides_a_perfect_ratio():
    score = score_of(10, 10, Decimal("0.90"), forced_failure=True)
    assert score.value == Decimal("1")
    assert score.passed is False
    assert any("hard rule" in line for line in score.detail)


def test_format_report_marks_each_measure():
    text = format_report("t", {"a": Score(Decimal("1"), Decimal("0.9"), True)})
    assert "OK  a" in text
    assert "100.00%" in text


@pytest.mark.parametrize("target", ["0.80", "0.90"])
def test_score_target_is_a_decimal_not_a_float(target):
    score = Score(Decimal("0.95"), Decimal(target), True)
    assert isinstance(score.target, Decimal)
