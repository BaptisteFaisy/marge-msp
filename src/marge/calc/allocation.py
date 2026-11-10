"""Tooling cost allocation (spec 12.2, EF-REF-03).

Domain layer: standard library only.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from ..domain import AllocationBasis, ToolingCost, money, ratio
from .inputs import MarginInputs


def _allocate_one(cost: ToolingCost, inputs: MarginInputs) -> Decimal:
    basis = cost.basis
    if basis == AllocationBasis.PER_CLIENT:
        divisor = Decimal(inputs.active_client_count) if inputs.active_client_count > 0 else Decimal(1)
        return money(cost.monthly_cost / divisor)

    if basis == AllocationBasis.PER_ACCOUNT:
        if cost.aws_account_id:
            matching = [c for c in inputs.aws_costs if c.aws_account_id == cost.aws_account_id]
            return cost.monthly_cost if matching else Decimal("0")
        divisor = Decimal(inputs.active_client_count) if inputs.active_client_count > 0 else Decimal(1)
        return money(cost.monthly_cost / divisor)

    if basis == AllocationBasis.PER_MANAGED_RESOURCE:
        if inputs.total_managed_resources > 0 and inputs.client.managed_resource_count > 0:
            share = ratio(
                Decimal(inputs.client.managed_resource_count),
                Decimal(inputs.total_managed_resources),
            )
            return money(cost.monthly_cost * share)
        divisor = Decimal(inputs.active_client_count) if inputs.active_client_count > 0 else Decimal(1)
        return money(cost.monthly_cost / divisor)

    # PER_LABOUR_HOUR default
    client_hours = sum((i.hours_spent for i in inputs.interventions), Decimal("0"))
    if inputs.total_msp_hours > Decimal("0") and client_hours > Decimal("0"):
        share = ratio(client_hours, inputs.total_msp_hours)
        return money(cost.monthly_cost * share)

    divisor = Decimal(inputs.active_client_count) if inputs.active_client_count > 0 else Decimal(1)
    return money(cost.monthly_cost / divisor)


def allocate_tooling(costs: Sequence[ToolingCost], inputs: MarginInputs) -> Decimal:
    """Return the total tooling cost allocated to this client for this month."""
    total = Decimal("0")
    for cost in costs:
        if cost.client_id is not None:
            if cost.client_id == inputs.client.client_id:
                total += cost.monthly_cost
            continue
        total += _allocate_one(cost, inputs)
    return money(total)
