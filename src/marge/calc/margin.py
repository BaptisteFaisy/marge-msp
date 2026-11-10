"""The per-client monthly margin calculation (spec 12, EF-CAL-01..04).

Domain layer: standard library only.
"""

from __future__ import annotations

from decimal import Decimal

from ..domain import (
    AwsCostKind,
    ContractStatus,
    CostBreakdown,
    InvoiceKind,
    MarginMonth,
    MarginState,
    RevenueBreakdown,
    Settings,
    money,
)
from .allocation import allocate_tooling
from .coverage import compute_coverage
from .inputs import MarginInputs
from .rates import rate_in_force


def _compute_revenue(inputs: MarginInputs) -> RevenueBreakdown:
    contract = inputs.contract
    sub = (
        contract.fields.monthly_subscription
        if (contract and contract.status == ContractStatus.VALIDATED)
        else Decimal("0")
    )
    resale = sum(
        (c.resale_margin for c in inputs.aws_costs if c.kind == AwsCostKind.CLIENT_ACCOUNT),
        Decimal("0"),
    )
    extra = sum(
        (i.amount for i in inputs.invoices if i.kind == InvoiceKind.EXTRA_HOURS),
        Decimal("0"),
    )
    projects = sum(
        (i.amount for i in inputs.invoices if i.kind == InvoiceKind.PROJECT),
        Decimal("0"),
    )
    return RevenueBreakdown(
        subscription=money(sub),
        aws_resale_margin=money(resale),
        extra_hours_billed=money(extra),
        projects=money(projects),
    )


def _compute_labour(inputs: MarginInputs) -> Decimal:
    total = Decimal("0")
    for iv in inputs.interventions:
        rate = rate_in_force(inputs.rates, iv.level, inputs.month)
        hourly = rate.hourly_cost if rate else Decimal("0")
        total += iv.hours_spent * hourly
    return money(total)


def _compute_costs(inputs: MarginInputs) -> CostBreakdown:
    labour = _compute_labour(inputs)
    tooling = allocate_tooling(inputs.tooling_costs, inputs)
    msp_aws = sum(
        (c.cost for c in inputs.aws_costs if c.kind == AwsCostKind.MSP_TOOLING_ACCOUNT),
        Decimal("0"),
    )
    penalties = sum((p.amount for p in inputs.penalties), Decimal("0"))
    return CostBreakdown(
        labour=labour,
        tooling=tooling,
        msp_aws=money(msp_aws),
        penalties=money(penalties),
    )


def compute_margin_month(inputs: MarginInputs, settings: Settings) -> MarginMonth:
    """Compute the monthly margin for one client (EF-CAL-01)."""
    rev = _compute_revenue(inputs)
    costs = _compute_costs(inputs)
    cov = compute_coverage(inputs.interventions)

    state = MarginState.COMPLETE
    reason = ""

    contract = inputs.contract
    if contract is None or contract.status != ContractStatus.VALIDATED:
        state = MarginState.INCOMPLETE
        reason = "No validated contract for this month"
    elif cov.value < settings.coverage_floor and cov.total_hours > Decimal("0"):
        state = MarginState.ESTIMATE
        reason = f"Coverage {cov.percent}% is below floor {settings.coverage_floor * 100}%"

    return MarginMonth(
        client_id=inputs.client.client_id,
        month=inputs.month,
        revenue=rev,
        costs=costs,
        coverage=cov,
        account_manager_id=inputs.client.account_manager_id,
        calc_version=inputs.calculation_version,
        calculated_at=inputs.month.last_day(),
        state=state,
        incomplete_reason=reason,
    )
