"""Scenarios of EF-AGT-05: formulas and parameters, never a model-made number."""

from __future__ import annotations

from decimal import Decimal

import pytest

from marge.quicksight import SCENARIO_IDS, SCENARIOS, scenario_by_id
from marge.quicksight.scenarios import ScenarioBaseline, apply_scenario


def baseline() -> ScenarioBaseline:
    """A client-month: 4620 EUR of revenue, 3725 EUR of cost, 895 EUR of margin."""
    return ScenarioBaseline(
        client_id="c-001",
        month="2026-10",
        revenue_subscription=Decimal("4000"),
        revenue_aws_resale=Decimal("620"),
        revenue_extra_hours_billed=Decimal("0"),
        revenue_projects=Decimal("0"),
        revenue_total=Decimal("4620"),
        cost_labour=Decimal("3290"),
        cost_tooling=Decimal("340"),
        cost_msp_aws=Decimal("95"),
        cost_penalties=Decimal("0"),
        cost_total=Decimal("3725"),
        margin=Decimal("895"),
        margin_rate=Decimal("0.1937"),
    )


def test_two_scenarios_are_declared() -> None:
    assert SCENARIO_IDS == ("SC-PRICE-INCREASE", "SC-EFFORT-REDUCTION")


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_scenario_declares_a_parameter_and_a_formula(scenario_id: str) -> None:
    scenario = scenario_by_id(scenario_id)
    assert scenario.parameters
    assert scenario.formula
    assert scenario.requirement == "EF-AGT-05"


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_scenario_formula_is_computed_by_code(scenario_id: str) -> None:
    scenario = scenario_by_id(scenario_id)
    assert scenario.computed_by == "marge.quicksight.scenarios.apply_scenario"


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_scenario_parameter_is_bounded(scenario_id: str) -> None:
    for parameter in scenario_by_id(scenario_id).parameters:
        assert parameter.unit == "percent"
        assert Decimal(parameter.minimum) <= Decimal(parameter.default) <= Decimal(parameter.maximum)


def test_price_increase_raises_revenue_and_margin() -> None:
    """8 % on the 4000 EUR of subscription: 4620 + 320 = 4940, margin 1215."""
    result = apply_scenario("SC-PRICE-INCREASE", baseline(), Decimal("8"))
    assert result.revenue_total == Decimal("4940")
    assert result.cost_total == Decimal("3725")
    assert result.margin == Decimal("1215")
    assert result.margin_delta == Decimal("320")


def test_price_increase_keeps_the_cost_untouched() -> None:
    result = apply_scenario("SC-PRICE-INCREASE", baseline(), Decimal("10"))
    assert result.cost_total == baseline().cost_total


def test_effort_reduction_lowers_the_cost() -> None:
    result = apply_scenario("SC-EFFORT-REDUCTION", baseline(), Decimal("20"))
    assert result.cost_total == Decimal("3067.0")
    assert result.revenue_total == Decimal("4620")
    assert result.margin == Decimal("1553.0")


def test_effort_reduction_keeps_the_revenue_untouched() -> None:
    result = apply_scenario("SC-EFFORT-REDUCTION", baseline(), Decimal("50"))
    assert result.revenue_total == baseline().revenue_total


def test_scenario_result_carries_the_formula() -> None:
    result = apply_scenario("SC-EFFORT-REDUCTION", baseline(), Decimal("10"))
    assert result.formula == scenario_by_id("SC-EFFORT-REDUCTION").formula


def test_zero_percent_keeps_the_baseline() -> None:
    for scenario_id in SCENARIO_IDS:
        result = apply_scenario(scenario_id, baseline(), Decimal("0"))
        assert result.margin == baseline().margin


def test_scenario_unknown_id_raises() -> None:
    with pytest.raises(KeyError):
        apply_scenario("SC-NOPE", baseline(), Decimal("5"))


def test_scenario_spec_unknown_id_raises() -> None:
    with pytest.raises(KeyError):
        scenario_by_id("SC-NOPE")


def test_scenario_inputs_are_dataset_fields() -> None:
    """Every input of a scenario is a column of the monthly margin table."""
    from marge.quicksight import dataset_by_name

    columns = dataset_by_name("marge_client_mois").field_names
    for scenario in SCENARIOS:
        for field in scenario.inputs:
            assert field in columns, f"{scenario.scenario_id}.{field}"


def test_scenario_outputs_are_dataset_fields() -> None:
    from marge.quicksight import dataset_by_name

    columns = dataset_by_name("marge_client_mois").field_names
    for scenario in SCENARIOS:
        for field in scenario.outputs:
            assert field in columns, f"{scenario.scenario_id}.{field}"
