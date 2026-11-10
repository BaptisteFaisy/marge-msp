"""Traceability: breaking down a margin figure into source lines (ENF-TRA-01).

Domain layer: standard library only.
"""

from __future__ import annotations

from decimal import Decimal

from ..domain import AwsCostKind, ContractStatus, MarginLine, MarginMonth, money
from .allocation import allocate_tooling
from .inputs import MarginInputs
from .rates import rate_in_force


def _revenue_lines(inputs: MarginInputs) -> list[MarginLine]:
    lines: list[MarginLine] = []
    contract = inputs.contract
    if contract and contract.status == ContractStatus.VALIDATED:
        lines.append(
            MarginLine(
                post="revenue.subscription",
                label=f"Contract {contract.contract_id} v{contract.version} subscription",
                amount=contract.fields.monthly_subscription,
                source_kind="contract",
                source_id=contract.contract_id,
            )
        )
    for cost in inputs.aws_costs:
        if cost.kind == AwsCostKind.CLIENT_ACCOUNT and cost.resale_margin != Decimal("0"):
            lines.append(
                MarginLine(
                    post="revenue.aws_resale",
                    label=f"AWS account {cost.aws_account_id} resale margin",
                    amount=cost.resale_margin,
                    source_kind="billing",
                    source_id=cost.aws_account_id,
                )
            )
    for inv in inputs.invoices:
        lines.append(
            MarginLine(
                post=f"revenue.{inv.kind.value.lower()}",
                label=f"Invoice {inv.invoice_id} ({inv.kind.value})",
                amount=inv.amount,
                source_kind="invoice",
                source_id=inv.invoice_id,
            )
        )
    return lines


def _cost_lines(inputs: MarginInputs) -> list[MarginLine]:
    lines: list[MarginLine] = []
    for iv in inputs.interventions:
        rate = rate_in_force(inputs.rates, iv.level, inputs.month)
        hourly = rate.hourly_cost if rate else Decimal("0")
        lines.append(
            MarginLine(
                post="cost.labour",
                label=f"Ticket {iv.ticket_id} ({iv.category}, {iv.level.value}, {iv.hours_spent}h)",
                amount=money(iv.hours_spent * hourly),
                source_kind="itsm",
                source_id=iv.intervention_id,
            )
        )
    tooling = allocate_tooling(inputs.tooling_costs, inputs)
    if tooling != Decimal("0"):
        lines.append(
            MarginLine(
                post="cost.tooling",
                label="Allocated MSP tooling",
                amount=tooling,
                source_kind="tooling",
                source_id=inputs.client.client_id,
            )
        )
    for cost in inputs.aws_costs:
        if cost.kind == AwsCostKind.MSP_TOOLING_ACCOUNT:
            lines.append(
                MarginLine(
                    post="cost.msp_aws",
                    label=f"MSP dedicated tooling AWS account {cost.aws_account_id}",
                    amount=cost.cost,
                    source_kind="billing",
                    source_id=cost.aws_account_id,
                )
            )
    for pen in inputs.penalties:
        lines.append(
            MarginLine(
                post="cost.penalties",
                label=f"Penalty: {pen.reason or 'SLA breach'}",
                amount=pen.amount,
                source_kind="penalty",
                source_id=inputs.client.client_id,
            )
        )
    return lines


def margin_lines(month: MarginMonth, inputs: MarginInputs) -> list[MarginLine]:  # noqa: ARG001
    """Every source line behind the monthly margin."""
    return _revenue_lines(inputs) + _cost_lines(inputs)
