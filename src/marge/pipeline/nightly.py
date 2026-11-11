"""The nightly run (spec 8.2).

1. Load the new tickets, worklogs and AWS costs.
2. Classify every intervention against the scope of its client's contract.
3. Recompute the margin and refresh the five analytical tables.
4. Report what is still waiting for a human.

The pipeline never talks to a model directly: it receives a ``classifier``
callable, so the same code runs with a real Bedrock model in production and
with a deterministic double in tests.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import date
from decimal import Decimal

from ..calc import (
    build_renewal_watch,
    compute_effort_slices,
    compute_hours_summary,
    compute_margin_month,
    margin_lines,
)
from ..domain import Classification, Contract, DecisionStatus, Intervention, Month, Settings
from ..store.base import Store
from .assemble import assemble_inputs, months_present
from .reports import LoadReport, NightlyReport

Classifier = Callable[[Intervention, Contract], Classification]
Loader = Callable[[Store, Settings, Month], list[LoadReport]]


def _target_month(store: Store, month: Month | None) -> Month:
    if month is not None:
        return month
    present = months_present(store)
    return present[-1] if present else Month.of(date.today())


def classify_pending(
    store: Store,
    settings: Settings,  # noqa: ARG001 - part of the stable pipeline signature
    month: Month,
    classifier: Classifier | None,
) -> tuple[int, int, int]:
    """Classify every intervention of the month that has no classification yet.

    Returns ``(classified, reused_decisions, queued_for_validation)``.
    An intervention whose client has no validated contract is left alone: it
    will be classified once a human validates the contract (EF-CTR-03).
    """
    if classifier is None:
        return (0, 0, 0)
    already = {c.intervention_id for c in store.list_classifications(month=month)}
    classified = reused = queued = 0
    for intervention in store.list_interventions(month=month):
        if intervention.intervention_id in already or not intervention.attributed:
            continue
        contract = store.active_contract(intervention.client_id or "", month)
        if contract is None:
            continue
        result = classifier(intervention, contract)
        store.save_classification(result)
        classified += 1
        reused += int(result.decided_by_memory)
        queued += int(result.needs_human_validation and result.status == DecisionStatus.PENDING)
    return (classified, reused, queued)


def recalculate_month(
    store: Store,
    settings: Settings,
    month: Month,
    calc_version: int = 1,
    today: object | None = None,
) -> tuple[int, int, Decimal]:
    """Recompute every client of one month and persist the five tables."""
    margins = []
    written = 0
    for client in store.list_clients():
        inputs = assemble_inputs(store, client, month, calc_version)
        row = compute_margin_month(inputs, settings)
        margins.append(row)
        store.save_margin_months([row])
        store.save_hours_summaries([compute_hours_summary(inputs, settings)])
        store.save_effort_slices(compute_effort_slices(inputs, settings))
        _save_lines(store, row, inputs)
        written += 1

    store.save_renewal_watch(
        build_renewal_watch(
            store.list_contracts(),
            margins,
            today if today is not None else month.last_day(),
            settings.renewal_horizon_days,
        )
    )
    coverage = _month_coverage(store, month)
    return (len(margins), written, coverage)


def _save_lines(store: Store, row: object, inputs: object) -> None:
    saver = getattr(store, "save_margin_lines", None)
    if callable(saver):
        saver(row.client_id, row.month, margin_lines(row, inputs))  # type: ignore[arg-type]


def _month_coverage(store: Store, month: Month) -> Decimal:
    from ..calc import compute_coverage

    coverage = compute_coverage(store.list_interventions(month=month))
    return coverage.percent


def run_nightly(
    store: Store,
    settings: Settings,
    month: Month | None = None,
    classifier: Classifier | None = None,
    loader: Loader | None = None,
    calc_version: int = 1,
) -> NightlyReport:
    """Run one nightly cycle and return its report (ENF-PERF-01 target: 30 min)."""
    started = time.monotonic()
    target = _target_month(store, month)
    report = NightlyReport(month=target)

    if loader is not None:
        report.loads = list(loader(store, settings, target))

    classified, reused, queued = classify_pending(store, settings, target, classifier)
    report.classified, report.reused_decisions, report.queued_for_validation = (
        classified,
        reused,
        queued,
    )

    clients, written, coverage = recalculate_month(store, settings, target, calc_version)
    report.clients_recalculated = clients
    report.margins_written = written
    report.coverage_percent = coverage
    report.duration_seconds = Decimal(round(time.monotonic() - started, 3))

    if coverage < settings.coverage_floor * 100:
        report.warnings.append(
            f"Coverage {coverage}% is below the {settings.coverage_floor * 100}% floor: "
            "months are flagged as estimates."
        )
    if queued:
        report.warnings.append(f"{queued} classification(s) await a human decision (EF-CLS-03).")
    return report
