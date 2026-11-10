"""Inputs of the margin model for one client-month.

Contains every element required to compute `MarginMonth`, `HoursSummary`,
`EffortSlice` and `list[MarginLine]` deterministically (spec 12, EF-CAL-01..05).

Domain layer: standard library only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from ..domain import (
    AwsCost,
    Classification,
    Client,
    Contract,
    Intervention,
    Invoice,
    Month,
    Penalty,
    Rate,
    ToolingCost,
)


@dataclass(frozen=True, slots=True)
class MarginInputs:
    """Every piece of evidence for client ``client_id`` during ``month``."""

    client: Client
    month: Month
    contract: Contract | None
    interventions: tuple[Intervention, ...] = ()
    classifications: tuple[Classification, ...] = ()
    aws_costs: tuple[AwsCost, ...] = ()
    invoices: tuple[Invoice, ...] = ()
    penalties: tuple[Penalty, ...] = ()
    rates: tuple[Rate, ...] = ()
    tooling_costs: tuple[ToolingCost, ...] = ()
    total_msp_hours: Decimal = Decimal("0")
    total_managed_resources: int = 0
    active_client_count: int = 1
    client_aws_account_count: int = 1
    calculation_version: int = 1

    @classmethod
    def assemble(
        cls,
        client: Client,
        month: Month,
        contract: Contract | None,
        interventions: Sequence[Intervention] = (),
        classifications: Sequence[Classification] = (),
        aws_costs: Sequence[AwsCost] = (),
        invoices: Sequence[Invoice] = (),
        penalties: Sequence[Penalty] = (),
        rates: Sequence[Rate] = (),
        tooling_costs: Sequence[ToolingCost] = (),
        total_msp_hours: Decimal = Decimal("0"),
        total_managed_resources: int = 0,
        active_client_count: int = 1,
        client_aws_account_count: int = 1,
        calculation_version: int = 1,
    ) -> MarginInputs:
        return cls(
            client=client,
            month=month,
            contract=contract,
            interventions=tuple(interventions),
            classifications=tuple(classifications),
            aws_costs=tuple(aws_costs),
            invoices=tuple(invoices),
            penalties=tuple(penalties),
            rates=tuple(rates),
            tooling_costs=tuple(tooling_costs),
            total_msp_hours=total_msp_hours,
            total_managed_resources=total_managed_resources,
            active_client_count=active_client_count,
            client_aws_account_count=client_aws_account_count,
            calculation_version=calculation_version,
        )


@dataclass(slots=True)
class AllocationContext:
    """Helper for distributing shared tooling costs across clients."""

    total_labour_hours: Decimal
    total_managed_resources: int
    total_clients: int
    tooling_costs: list[ToolingCost] = field(default_factory=list)
