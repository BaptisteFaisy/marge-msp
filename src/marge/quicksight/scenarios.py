"""Simulation scenarios (EF-AGT-05).

Two scenarios are shipped: a price increase and a reduction of the effort.
Each scenario carries its parameters and its **formula**. The formula is
evaluated by this module, on the server, with :class:`~decimal.Decimal` — the
language model never computes a figure (ENF-IA-01, spec 4.2).

The baseline values come from the datasets of Annex A; this module never
recomputes a margin, it only applies a documented delta to figures already
produced by ``marge.calc``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import ParameterSpec, ScenarioSpec

__all__ = [
    "SCENARIOS",
    "SCENARIO_IDS",
    "ScenarioBaseline",
    "ScenarioResult",
    "apply_scenario",
    "scenario_by_id",
]

_HUNDRED = Decimal("100")


@dataclass(frozen=True, slots=True)
class ScenarioBaseline:
    """The figures a scenario is applied to, read from the analytical tables."""

    client_id: str
    month: str
    revenue_subscription: Decimal
    revenue_aws_resale: Decimal
    revenue_extra_hours_billed: Decimal
    revenue_projects: Decimal
    revenue_total: Decimal
    cost_labour: Decimal
    cost_tooling: Decimal
    cost_msp_aws: Decimal
    cost_penalties: Decimal
    cost_total: Decimal
    margin: Decimal
    margin_rate: Decimal

    @property
    def msp_priced_revenue(self) -> Decimal:
        """Revenue whose price the MSP sets: the AWS resale margin is passed through."""
        return self.revenue_subscription + self.revenue_extra_hours_billed + self.revenue_projects


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    """The outcome of one scenario, computed by code."""

    scenario_id: str
    client_id: str
    month: str
    parameter: str
    parameter_value: Decimal
    revenue_total: Decimal
    cost_total: Decimal
    margin: Decimal
    margin_rate: Decimal
    margin_delta: Decimal
    margin_rate_delta: Decimal
    formula: str


_SCENARIOS: tuple[ScenarioSpec, ...] = (
    ScenarioSpec(
        scenario_id="SC-PRICE-INCREASE",
        title="Price increase",
        requirement="EF-AGT-05",
        description=(
            "Effect of a price increase on the monthly margin of a client. The increase applies "
            "to the revenue the MSP prices itself: subscription, extra hours and projects. The "
            "AWS resale margin is passed through and the costs are unchanged."
        ),
        parameters=(
            ParameterSpec(
                name="price_increase_pct",
                data_type="decimal",
                default="8",
                minimum="0",
                maximum="50",
                unit="percent",
                description="Increase applied to the MSP-priced revenue of the client-month.",
            ),
        ),
        formula=(
            "revenue_total' = revenue_total + msp_priced_revenue * price_increase_pct / 100 ; "
            "cost_total' = cost_total ; "
            "margin' = revenue_total' - cost_total' ; "
            "margin_rate' = margin' / revenue_total'"
        ),
        inputs=(
            "revenue_subscription",
            "revenue_aws_resale",
            "revenue_extra_hours_billed",
            "revenue_projects",
            "revenue_total",
            "cost_total",
        ),
        outputs=("revenue_total", "cost_total", "margin", "margin_rate"),
        computed_by="marge.quicksight.scenarios.apply_scenario",
        note="The agent quotes the formula and the parameters; the figures come from this module.",
    ),
    ScenarioSpec(
        scenario_id="SC-EFFORT-REDUCTION",
        title="Effort reduction",
        requirement="EF-AGT-05",
        description=(
            "Effect of a reduction of the effort on the monthly margin of a client. The labour "
            "cost falls in proportion to the effort; the tooling, the AWS carried by the MSP and "
            "the penalties are unchanged."
        ),
        parameters=(
            ParameterSpec(
                name="effort_reduction_pct",
                data_type="decimal",
                default="20",
                minimum="0",
                maximum="80",
                unit="percent",
                description="Reduction applied to the labour cost of the client-month.",
            ),
        ),
        formula=(
            "cost_labour' = cost_labour * (1 - effort_reduction_pct / 100) ; "
            "cost_total' = cost_total - cost_labour + cost_labour' ; "
            "revenue_total' = revenue_total ; "
            "margin' = revenue_total - cost_total' ; "
            "margin_rate' = margin' / revenue_total"
        ),
        inputs=("cost_labour", "cost_total", "revenue_total"),
        outputs=("revenue_total", "cost_total", "margin", "margin_rate"),
        computed_by="marge.quicksight.scenarios.apply_scenario",
        note="The agent quotes the formula and the parameters; the figures come from this module.",
    ),
)

SCENARIOS: tuple[ScenarioSpec, ...] = _SCENARIOS

SCENARIO_IDS: tuple[str, ...] = tuple(scenario.scenario_id for scenario in SCENARIOS)


def scenario_by_id(scenario_id: str) -> ScenarioSpec:
    """Return the scenario ``scenario_id`` or raise ``KeyError``."""
    for scenario in SCENARIOS:
        if scenario.scenario_id == scenario_id:
            return scenario
    raise KeyError(f"no scenario named {scenario_id!r}")


def _price_increase(baseline: ScenarioBaseline, pct: Decimal) -> ScenarioResult:
    """Apply a price increase to the baseline of a client-month."""
    revenue = baseline.revenue_total + baseline.msp_priced_revenue * pct / _HUNDRED
    margin = revenue - baseline.cost_total
    rate = (margin / revenue) if revenue != 0 else Decimal("0")
    return ScenarioResult(
        scenario_id="SC-PRICE-INCREASE",
        client_id=baseline.client_id,
        month=baseline.month,
        parameter="price_increase_pct",
        parameter_value=pct,
        revenue_total=revenue,
        cost_total=baseline.cost_total,
        margin=margin,
        margin_rate=rate,
        margin_delta=margin - baseline.margin,
        margin_rate_delta=rate - baseline.margin_rate,
        formula=scenario_by_id("SC-PRICE-INCREASE").formula,
    )


def _effort_reduction(baseline: ScenarioBaseline, pct: Decimal) -> ScenarioResult:
    """Apply an effort reduction to the baseline of a client-month."""
    labour = baseline.cost_labour * (Decimal("1") - pct / _HUNDRED)
    cost = baseline.cost_total - baseline.cost_labour + labour
    margin = baseline.revenue_total - cost
    rate = (margin / baseline.revenue_total) if baseline.revenue_total != 0 else Decimal("0")
    return ScenarioResult(
        scenario_id="SC-EFFORT-REDUCTION",
        client_id=baseline.client_id,
        month=baseline.month,
        parameter="effort_reduction_pct",
        parameter_value=pct,
        revenue_total=baseline.revenue_total,
        cost_total=cost,
        margin=margin,
        margin_rate=rate,
        margin_delta=margin - baseline.margin,
        margin_rate_delta=rate - baseline.margin_rate,
        formula=scenario_by_id("SC-EFFORT-REDUCTION").formula,
    )


def apply_scenario(scenario_id: str, baseline: ScenarioBaseline, pct: Decimal) -> ScenarioResult:
    """Apply the scenario ``scenario_id`` to ``baseline`` with ``pct``.

    The arithmetic happens here, on the server, with ``Decimal``: the model
    only asks for a simulation, it never produces the figure (ENF-IA-01).
    """
    if scenario_id == "SC-PRICE-INCREASE":
        return _price_increase(baseline, pct)
    if scenario_id == "SC-EFFORT-REDUCTION":
        return _effort_reduction(baseline, pct)
    raise KeyError(f"no scenario named {scenario_id!r}")
