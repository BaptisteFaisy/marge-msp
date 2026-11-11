"""Per-client margins of a loaded dataset, computed with ``marge.calc`` (spec 12).

Neither the generator nor the harness ever invents a figure: this module
assembles :class:`~marge.calc.MarginInputs` from the records of a
:class:`~marge.eval.dataset.Dataset` and lets the calculation engine produce
every margin (ENF-IA-01). It is the shared query layer behind the reference
questions, the renewal watch and the seeded-situation checks.

Rules that belong to loading, applied here:

* the hours of an intervention whose ITSM reference could not be resolved stay
  in the ``UNASSIGNED`` bucket, never spread over clients (EF-REF-04);
* a ticket typed without a customer reference but naming the client still
  counts in that client's coverage, otherwise a data-entry problem would look
  like a perfectly covered month (spec 12.4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from ..calc import MarginInputs, build_renewal_watch, compute_hours_summary, compute_margin_month
from ..domain import (
    UNASSIGNED_CLIENT_ID,
    AwsCost,
    AwsCostKind,
    Classification,
    Contract,
    HoursSummary,
    MarginMonth,
    Month,
    RenewalWatch,
    Settings,
    WorkClass,
    hours,
)
from .dataset import Dataset
from .local_classifier import classify

SETTINGS = Settings()


def month_of(day: date) -> str:
    """``date(2026, 5, 4)`` -> ``2026-05``."""
    return f"{day.year:04d}-{day.month:02d}"


@dataclass(slots=True)
class MarginReport:
    """Every client-month margin, plus the derived figures of the demo."""

    dataset: Dataset
    settings: Settings = field(default_factory=lambda: SETTINGS)
    months: list[str] = field(default_factory=list)
    margins: list[MarginMonth] = field(default_factory=list)
    classifications: list[Classification] = field(default_factory=list)
    summaries: dict[tuple[str, str], HoursSummary] = field(default_factory=dict)
    oos_by_category: dict[tuple[str, str], dict[str, Decimal]] = field(default_factory=dict)
    unassigned_hours: dict[str, Decimal] = field(default_factory=dict)
    contracts_in_force: dict[tuple[str, str], Contract] = field(default_factory=dict)
    total_msp_hours: dict[str, Decimal] = field(default_factory=dict)

    # -- lookups -----------------------------------------------------------
    def get(self, client_id: str, month: str) -> MarginMonth | None:
        return next(
            (row for row in self.margins if row.client_id == client_id and str(row.month) == month),
            None,
        )

    def series(self, client_id: str) -> list[MarginMonth]:
        return sorted((row for row in self.margins if row.client_id == client_id), key=lambda row: row.month)

    def client_ids(self) -> list[str]:
        return [client.client_id for client in self.dataset.clients]

    def renewals(self, today: date, horizon_days: int = 90) -> list[RenewalWatch]:
        """Contracts renewing soon, with their six-month margin and trend."""
        latest: dict[str, Contract] = {}
        for contract in self.contracts_in_force.values():
            current = latest.get(contract.client_id)
            if current is None or contract.version > current.version:
                latest[contract.client_id] = contract
        return build_renewal_watch(list(latest.values()), self.margins, today, horizon_days)

    def out_of_scope_hours(self, client_id: str) -> Decimal:
        total = sum(
            (
                sum(categories.values(), Decimal("0"))
                for (owner, _month), categories in self.oos_by_category.items()
                if owner == client_id
            ),
            Decimal("0"),
        )
        return hours(total)

    def out_of_scope_by_category(self, client_id: str) -> dict[str, Decimal]:
        totals: dict[str, Decimal] = {}
        for (owner, _month), categories in self.oos_by_category.items():
            if owner != client_id:
                continue
            for name, value in categories.items():
                totals[name] = totals.get(name, Decimal("0")) + value
        return {name: hours(value) for name, value in totals.items()}


def _interventions_of(dataset: Dataset, month: str) -> list:
    return [item for item in dataset.interventions if month_of(item.occurred_on) == month]


def _total_resources(dataset: Dataset) -> int:
    return sum(client.managed_resource_count for client in dataset.clients)


def _msp_aws_share(dataset: Dataset, month: str, client) -> AwsCost:
    """MSP-owned tooling accounts, spread over clients by managed resources."""
    tooling = [
        cost
        for cost in dataset.aws_costs
        if cost.kind == AwsCostKind.MSP_TOOLING_ACCOUNT and str(cost.month) == month
    ]
    total = sum((cost.cost for cost in tooling), Decimal("0"))
    resources = _total_resources(dataset)
    share = total * Decimal(client.managed_resource_count) / Decimal(max(1, resources))
    return AwsCost(
        aws_account_id="msp-tooling",
        month=Month.parse(month),
        cost=share,
        kind=AwsCostKind.MSP_TOOLING_ACCOUNT,
        currency="EUR",
    )


def _inputs_for(report: MarginReport, client_id: str, month: str) -> MarginInputs:
    dataset = report.dataset
    client = dataset.client(client_id)
    rows = _interventions_of(dataset, month)
    own = [item for item in rows if item.client_id == client_id]
    borrowed = [
        item
        for item in rows
        if item.client_id == UNASSIGNED_CLIENT_ID and dataset.owners.get(item.intervention_id) == client_id
    ]
    aws = [
        cost
        for cost in dataset.aws_costs
        if cost.kind == AwsCostKind.CLIENT_ACCOUNT
        and cost.client_id == client_id
        and str(cost.month) == month
    ]
    aws.append(_msp_aws_share(dataset, month, client))
    return MarginInputs.assemble(
        client=client,
        month=Month.parse(month),
        contract=report.contracts_in_force.get((client_id, month)),
        interventions=own + borrowed,
        aws_costs=aws,
        invoices=[
            invoice
            for invoice in dataset.invoices
            if invoice.client_id == client_id and str(invoice.month) == month
        ],
        penalties=[
            penalty
            for penalty in dataset.penalties
            if penalty.client_id == client_id and str(penalty.month) == month
        ],
        rates=dataset.rates,
        tooling_costs=dataset.tooling,
        total_msp_hours=report.total_msp_hours.get(month, Decimal("0")),
        total_managed_resources=_total_resources(dataset),
        active_client_count=len(dataset.clients),
        client_aws_account_count=1,
    )


def _with_classifications(inputs: MarginInputs, rows: list[Classification]) -> MarginInputs:
    """``MarginInputs`` is frozen: rebuild it with the classifications attached."""
    return MarginInputs(
        client=inputs.client,
        month=inputs.month,
        contract=inputs.contract,
        interventions=inputs.interventions,
        classifications=tuple(rows),
        aws_costs=inputs.aws_costs,
        invoices=inputs.invoices,
        penalties=inputs.penalties,
        rates=inputs.rates,
        tooling_costs=inputs.tooling_costs,
        total_msp_hours=inputs.total_msp_hours,
        total_managed_resources=inputs.total_managed_resources,
        active_client_count=inputs.active_client_count,
        client_aws_account_count=inputs.client_aws_account_count,
        calculation_version=inputs.calculation_version,
    )


def _classify_all(report: MarginReport) -> None:
    for item in report.dataset.interventions:
        if item.client_id == UNASSIGNED_CLIENT_ID:
            continue
        month = month_of(item.occurred_on)
        contract = report.contracts_in_force.get((item.client_id, month))
        classification = classify(item, contract, report.settings)
        report.classifications.append(classification)
        if classification.work_class == WorkClass.OUT_OF_SCOPE:
            bucket = report.oos_by_category.setdefault((item.client_id, month), {})
            bucket[item.category] = bucket.get(item.category, Decimal("0")) + item.hours_spent


def build_report(dataset: Dataset, settings: Settings | None = None) -> MarginReport:
    """Compute every client-month margin of ``dataset`` (spec 12)."""
    report = MarginReport(dataset=dataset, settings=settings or SETTINGS)
    report.months = dataset.months_present()
    report.contracts_in_force = {
        (client.client_id, month): contract
        for client in dataset.clients
        for month in report.months
        if (contract := dataset.contract_for(client.client_id, month)) is not None
    }
    for month in report.months:
        rows = _interventions_of(dataset, month)
        report.total_msp_hours[month] = hours(sum((item.hours_spent for item in rows), Decimal("0")))
        report.unassigned_hours[month] = hours(
            sum(
                (item.hours_spent for item in rows if item.client_id == UNASSIGNED_CLIENT_ID),
                Decimal("0"),
            )
        )
    _classify_all(report)
    for month in report.months:
        for client in dataset.clients:
            inputs = _with_classifications(
                _inputs_for(report, client.client_id, month),
                [item for item in report.classifications if item.client_id == client.client_id],
            )
            report.margins.append(compute_margin_month(inputs, report.settings))
            report.summaries[(client.client_id, month)] = compute_hours_summary(inputs, report.settings)
    return report
