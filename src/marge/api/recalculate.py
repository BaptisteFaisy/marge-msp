"""On-demand recalculation endpoint logic (spec 12, 16, EF-CAL-01..03).

Assembles ``MarginInputs`` from the ``Store``, invokes ``marge.calc`` to
compute ``MarginMonth``, ``HoursSummary``, ``EffortSlice`` and ``MarginLine``,
and persists the outputs back into the ``Store`` alongside an ``AuditEntry``.
"""

from __future__ import annotations

from decimal import Decimal

from ..calc import (
    CalcVersion,
    MarginInputs,
    compute_effort_slices,
    compute_hours_summary,
    compute_margin_month,
    margin_lines,
)
from ..domain import (
    AuditEntry,
    AwsCostKind,
    Client,
    Month,
    Settings,
)
from ..store.base import Store
from .auth import Actor


def _next_calc_version(store: Store, month: Month) -> int:
    existing = store.list_margin_months(month=month)
    if not existing:
        return 1
    return max(r.calc_version for r in existing) + 1


def _client_inputs(
    store: Store,
    client: Client,
    month: Month,
    all_clients: list[Client],
    total_msp_hours: Decimal,
    calc_version: int,
) -> MarginInputs:
    contract = store.active_contract(client.client_id, month)
    interventions = store.list_interventions(month=month, client_id=client.client_id)
    classifications = store.list_classifications(client_id=client.client_id, month=month)
    all_aws = store.list_aws_costs(month=month)
    client_aws = [c for c in all_aws if c.client_id == client.client_id]
    invoices = [inv for inv in store.list_invoices(month=month) if inv.client_id == client.client_id]
    penalties = [p for p in store.list_penalties(month=month) if p.client_id == client.client_id]
    rates = store.list_rates()
    tooling = store.list_tooling_costs()
    total_resources = sum(c.managed_resource_count for c in all_clients)
    aws_accounts = len({c.aws_account_id for c in client_aws if c.kind == AwsCostKind.CLIENT_ACCOUNT})

    return MarginInputs.assemble(
        client=client,
        month=month,
        contract=contract,
        interventions=interventions,
        classifications=classifications,
        aws_costs=client_aws,
        invoices=invoices,
        penalties=penalties,
        rates=rates,
        tooling_costs=tooling,
        total_msp_hours=total_msp_hours,
        total_managed_resources=total_resources,
        active_client_count=max(len(all_clients), 1),
        client_aws_account_count=max(aws_accounts, 1),
        calculation_version=calc_version,
    )


def run_recalculate(
    store: Store,
    settings: Settings,
    actor: Actor,
    month_str: str,
    client_id: str | None = None,
    reason: str = "on-demand recalculation",
) -> tuple[int, int]:
    """Run ``marge.calc`` for one month and persist results to ``store``.

    Returns ``(calculated_clients, calc_version)``.
    """
    month = Month.parse(month_str)
    all_clients = store.list_clients()
    targets = [c for c in all_clients if client_id is None or c.client_id == client_id]
    all_interventions = store.list_interventions(month=month)
    total_msp_hours = sum((i.hours_spent for i in all_interventions), Decimal("0"))
    calc_version = _next_calc_version(store, month)

    margin_rows = []
    effort_rows = []
    hours_rows = []

    for client in targets:
        inputs = _client_inputs(store, client, month, all_clients, total_msp_hours, calc_version)
        margin_row = compute_margin_month(inputs, settings)
        margin_rows.append(margin_row)
        effort_rows.extend(compute_effort_slices(inputs, settings))
        hours_rows.append(compute_hours_summary(inputs, settings))
        set_lines = getattr(store, "set_margin_lines", None)
        if callable(set_lines):
            set_lines(client.client_id, month, margin_lines(margin_row, inputs))

    store.save_margin_months(margin_rows)
    store.save_effort_slices(effort_rows)
    store.save_hours_summaries(hours_rows)
    _record_version(store, calc_version, month, client_id, actor, reason, len(margin_rows))
    return len(margin_rows), calc_version


def _record_version(
    store: Store,
    calc_version: int,
    month: Month,
    client_id: str | None,
    actor: Actor,
    reason: str,
    clients: int,
) -> None:
    """Open a dated, signed and motivated calculation version (EF-CAL-03).

    The past is never rewritten silently: the version row carries who asked,
    why and when, and ``GET /v1/calc-versions/diff`` shows what moved.
    """
    scope = f"{month}:{client_id or 'all'}"
    store.save_calc_version(
        CalcVersion.open(
            calc_version,
            actor.actor_id,
            reason or "recalculated from the portal",
            fingerprint=f"{scope}:{clients}",
        )
    )
    store.append(
        AuditEntry.now(
            entity_kind="calculation",
            entity_id=scope,
            action="recalculate",
            author=actor.actor_id,
            reason=reason,
            after={"calc_version": calc_version, "clients": clients},
        )
    )
