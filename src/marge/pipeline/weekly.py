"""The weekly validation round (spec 8.3).

Every account manager receives the list of interventions classified
``OUT_OF_SCOPE`` or ``UNCERTAIN`` for their own clients. Only the hours they
validate count as "detected unbilled hours".
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from ..domain import DecisionStatus, Month, Settings, WorkClass, money
from ..store.base import Store
from .reports import AccountManagerQueue, WeeklyReport

QUEUED_CLASSES = (WorkClass.OUT_OF_SCOPE, WorkClass.UNCERTAIN)


def pending_classifications(store: Store, month: Month | None = None) -> list[object]:
    """Classifications still waiting for a human, optionally for one month."""
    rows = [
        c
        for c in store.list_classifications(status=DecisionStatus.PENDING.value)
        if c.work_class in QUEUED_CLASSES
    ]
    if month is None:
        return rows
    wanted = {i.intervention_id for i in store.list_interventions(month=month)}
    return [c for c in rows if c.intervention_id in wanted]


def _hours_and_value(store: Store, classification: object) -> tuple[Decimal, Decimal]:
    intervention = next(
        (i for i in store.list_interventions() if i.intervention_id == classification.intervention_id),
        None,
    )
    if intervention is None:
        return (Decimal("0"), Decimal("0"))
    contract = store.active_contract(intervention.client_id or "", intervention.month)
    hourly = contract.fields.extra_hour_rate if contract else Decimal("0")
    return (intervention.hours_spent, money(intervention.hours_spent * hourly))


def build_queues(store: Store, month: Month | None = None) -> list[AccountManagerQueue]:
    """Group the pending classifications by account manager."""
    grouped: dict[str, list[object]] = defaultdict(list)
    for classification in pending_classifications(store, month):
        client = store.get_client(classification.client_id)
        if client is None:
            continue
        grouped[client.account_manager_id].append(classification)

    queues: list[AccountManagerQueue] = []
    for manager, rows in sorted(grouped.items()):
        clients: set[str] = set()
        ids: list[str] = []
        total_hours = Decimal("0")
        total_value = Decimal("0")
        for row in rows:
            clients.add(row.client_id)
            ids.append(row.intervention_id)
            spent, value = _hours_and_value(store, row)
            total_hours += spent
            total_value += value
        queues.append(
            AccountManagerQueue(
                account_manager_id=manager,
                client_ids=tuple(sorted(clients)),
                intervention_ids=tuple(sorted(ids)),
                hours=money(total_hours),
                value=money(total_value),
            )
        )
    return queues


def run_weekly(
    store: Store,
    settings: Settings,  # noqa: ARG001 - part of the stable pipeline signature
    month: Month | None = None,
) -> WeeklyReport:
    """Produce the weekly validation report (EF-CLS-03)."""
    queues = build_queues(store, month)
    return WeeklyReport(
        generated_on=date.today().isoformat(),
        queues=queues,
        pending_total=sum(len(q.intervention_ids) for q in queues),
        hours_total=money(sum((q.hours for q in queues), Decimal("0"))),
        value_total=money(sum((q.value for q in queues), Decimal("0"))),
    )


def below_validation_floor(store: Store, settings: Settings) -> int:
    """Count out-of-scope work shorter than the 15 minute floor (spec 13.2)."""
    count = 0
    for intervention in store.list_interventions():
        if intervention.hours_spent >= settings.min_hours_for_validation:
            continue
        classification = next(
            (c for c in store.list_classifications() if c.intervention_id == intervention.intervention_id),
            None,
        )
        if classification is not None and classification.work_class == WorkClass.OUT_OF_SCOPE:
            count += 1
    return count
