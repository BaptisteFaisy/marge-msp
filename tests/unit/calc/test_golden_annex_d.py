"""Golden numbers of Annex D (docs/SPEC.fr.md) must be reproduced exactly.

October 2026, one client:
revenue 4 620 EUR, cost 3 725 EUR, margin 895 EUR = 19.4 %,
9 validated out-of-scope hours worth 990 EUR.
"""

from __future__ import annotations

from decimal import Decimal

from tests.fakes.builders import golden_inputs, golden_settings

from marge.calc import compute_hours_summary, compute_margin_month, margin_lines


def test_golden_revenue_breakdown() -> None:
    result = compute_margin_month(golden_inputs(), golden_settings())
    assert result.revenue.subscription == Decimal("4000.00")
    assert result.revenue.aws_resale_margin == Decimal("620.00")
    assert result.revenue.total == Decimal("4620.00")


def test_golden_cost_breakdown() -> None:
    result = compute_margin_month(golden_inputs(), golden_settings())
    assert result.costs.labour == Decimal("3290.00")
    assert result.costs.tooling == Decimal("340.00")
    assert result.costs.msp_aws == Decimal("95.00")
    assert result.costs.penalties == Decimal("0.00")
    assert result.costs.total == Decimal("3725.00")


def test_golden_margin_and_rate() -> None:
    result = compute_margin_month(golden_inputs(), golden_settings())
    assert result.margin == Decimal("895.00")
    assert result.margin_rate == Decimal("0.1937")
    assert (result.margin_rate * 100).quantize(Decimal("0.1")) == Decimal("19.4")


def test_golden_month_is_complete() -> None:
    result = compute_margin_month(golden_inputs(), golden_settings())
    assert result.state.value == "COMPLETE"
    assert result.incomplete_reason == ""
    assert result.coverage.value == Decimal("1.0000")


def test_golden_unbilled_hours() -> None:
    summary = compute_hours_summary(golden_inputs(), golden_settings())
    assert summary.consumed_hours == Decimal("46.00")
    assert summary.out_of_scope_validated_hours == Decimal("9.00")
    assert summary.over_quota_hours == Decimal("0.00")
    assert summary.unbilled_hours == Decimal("9.00")
    assert summary.unbilled_value == Decimal("990.00")


def test_golden_margin_decomposes_to_source_lines() -> None:
    """ENF-TRA-01 — every figure goes back to a source line."""
    inputs = golden_inputs()
    result = compute_margin_month(inputs, golden_settings())
    lines = margin_lines(result, inputs)
    revenue = sum((line.amount for line in lines if line.post.startswith("revenue")), Decimal("0"))
    costs = sum((line.amount for line in lines if line.post.startswith("cost")), Decimal("0"))
    assert revenue == result.revenue.total
    assert costs == result.costs.total
    assert any(line.source_kind == "itsm" for line in lines)
    assert any(line.source_kind == "contract" for line in lines)
