"""Hours summary and unbilled hours detection (spec 12.3, EF-CAL-02, EF-TDB-03).

Domain layer: standard library only.
"""

from __future__ import annotations

from decimal import Decimal

from ..domain import (
    ContractStatus,
    DecisionStatus,
    HoursSummary,
    InvoiceKind,
    Settings,
    UnbilledState,
    WorkClass,
    hours,
    money,
)
from .inputs import MarginInputs


def compute_hours_summary(inputs: MarginInputs, settings: Settings) -> HoursSummary:  # noqa: ARG001
    """Compute quota consumption and unbilled hours for a client-month."""
    contract = inputs.contract
    has_valid_contract = contract is not None and contract.status == ContractStatus.VALIDATED

    included_quota = (
        contract.fields.included_hours_per_month
        if (has_valid_contract and contract.fields.included_hours_per_month is not None)
        else Decimal("0")
    )
    contract_hour_rate = contract.fields.extra_hour_rate if has_valid_contract else Decimal("0")

    class_map = {c.intervention_id: c for c in inputs.classifications}

    consumed_hours = Decimal("0")
    out_of_scope_validated = Decimal("0")

    for iv in inputs.interventions:
        cls = class_map.get(iv.intervention_id)
        if cls is not None:
            if cls.work_class == WorkClass.OUT_OF_SCOPE and cls.status == DecisionStatus.APPROVED:
                out_of_scope_validated += iv.hours_spent
            elif cls.work_class == WorkClass.INCLUDED:
                consumed_hours += iv.hours_spent
            else:
                consumed_hours += iv.hours_spent
        else:
            consumed_hours += iv.hours_spent

    billed_extra = sum(
        (i.hours_billed for i in inputs.invoices if i.kind == InvoiceKind.EXTRA_HOURS),
        Decimal("0"),
    )

    summary = HoursSummary(
        client_id=inputs.client.client_id,
        month=inputs.month,
        included_quota=hours(included_quota),
        consumed_hours=hours(consumed_hours),
        out_of_scope_validated_hours=hours(out_of_scope_validated),
        billed_extra_hours=hours(billed_extra),
        contract_hour_rate=money(contract_hour_rate),
        state=UnbilledState.DETECTED,
    )
    if summary.unbilled_hours == Decimal("0"):
        summary.state = UnbilledState.BILLED
    return summary
