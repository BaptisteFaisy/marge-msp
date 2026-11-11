"""Assembling the inputs of the margin model from a store (spec 12, 15).

This is the single place where a client-month is gathered: the nightly
pipeline, the portal's ``POST /v1/recalculate`` and the CLI all go through it,
so there is exactly one implementation of the assembly logic.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from ..calc import MarginInputs
from ..domain import Client, Contract, Month
from ..store.base import Store


def _account_ids(costs: Sequence[object]) -> set[str]:
    return {getattr(c, "aws_account_id", "") for c in costs} - {""}


def total_labour_hours(store: Store, month: Month) -> Decimal:
    """Every hour recorded in the month, attributed or not (allocation base)."""
    return sum((i.hours_spent for i in store.list_interventions(month=month)), Decimal("0"))


def total_managed_resources(store: Store) -> int:
    return sum(c.managed_resource_count for c in store.list_clients())


def client_aws_costs(store: Store, client: Client, month: Month) -> list[object]:
    """AWS costs of the month that belong to this client.

    A cost row is attached to the client either directly (``client_id``) or
    through the accounts the client's interventions touched.
    """
    interventions = store.list_interventions(month=month, client_id=client.client_id)
    accounts = {i.aws_account_id for i in interventions if i.aws_account_id}
    rows = []
    for cost in store.list_aws_costs(month=month):
        if cost.client_id == client.client_id or cost.aws_account_id in accounts:
            rows.append(cost)
    return rows


def assemble_inputs(
    store: Store,
    client: Client,
    month: Month,
    calc_version: int = 1,
) -> MarginInputs:
    """Gather every input of one client-month into ``MarginInputs``."""
    interventions = store.list_interventions(month=month, client_id=client.client_id)
    ids = {i.intervention_id for i in interventions}
    classifications = [
        c for c in store.list_classifications(client_id=client.client_id) if c.intervention_id in ids
    ]
    aws_costs = client_aws_costs(store, client, month)
    invoices = [i for i in store.list_invoices(month=month) if i.client_id == client.client_id]
    penalties = [p for p in store.list_penalties(month=month) if p.client_id == client.client_id]

    return MarginInputs(
        client=client,
        month=month,
        contract=store.active_contract(client.client_id, month),
        interventions=tuple(interventions),
        classifications=tuple(classifications),
        aws_costs=tuple(aws_costs),
        invoices=tuple(invoices),
        penalties=tuple(penalties),
        rates=tuple(store.list_rates()),
        tooling_costs=tuple(store.list_tooling_costs()),
        total_msp_hours=total_labour_hours(store, month),
        total_managed_resources=total_managed_resources(store),
        active_client_count=max(1, len(store.list_clients())),
        client_aws_account_count=max(1, len(_account_ids(aws_costs))),
        calculation_version=calc_version,
    )


def months_present(store: Store) -> list[Month]:
    """Every month for which at least one intervention exists, sorted."""
    return sorted({i.month for i in store.list_interventions()})


def contracts_of(store: Store, client_id: str) -> list[Contract]:
    return store.list_contracts(client_id)
