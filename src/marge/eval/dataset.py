"""Loader of the generated dataset (canonical interchange formats, DATA-FORMATS).

Reads ``data/generated/`` exactly as a connector would: CSV/JSON in, domain
dataclasses out. Two rules of the spec live here because they are *loading*
rules, not calculation rules:

* an intervention whose ``customer_ref`` is empty is never spread over clients
  silently: it goes to the ``UNASSIGNED`` bucket (EF-REF-04, spec 12.4);
* a ticket typed without a customer reference but naming the client in its
  description still counts in that client's coverage — otherwise a data-entry
  problem would look like a perfectly covered month.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from ..domain import (
    UNASSIGNED_CLIENT_ID,
    AllocationBasis,
    AwsCost,
    AwsCostKind,
    Client,
    Contract,
    ContractStatus,
    Intervention,
    Invoice,
    InvoiceKind,
    Month,
    Penalty,
    Rate,
    ToolingCost,
    WorkLevel,
)
from .local_extractor import extract_contract

MONTH_FILES = ("clients.json", "aliases.json", "interventions.csv")


@dataclass(slots=True)
class Dataset:
    """Every loaded record, plus the ownership map of each intervention."""

    root: Path
    clients: list[Client] = field(default_factory=list)
    interventions: list[Intervention] = field(default_factory=list)
    owners: dict[str, str] = field(default_factory=dict)
    contracts: list[Contract] = field(default_factory=list)
    aws_costs: list[AwsCost] = field(default_factory=list)
    invoices: list[Invoice] = field(default_factory=list)
    rates: list[Rate] = field(default_factory=list)
    tooling: list[ToolingCost] = field(default_factory=list)
    penalties: list[Penalty] = field(default_factory=list)
    fx: dict[str, Decimal] = field(default_factory=dict)
    expected_fields: list[dict] = field(default_factory=list)
    labels: list[dict] = field(default_factory=list)
    questions: list[dict] = field(default_factory=list)
    manifest: dict = field(default_factory=dict)

    @property
    def months(self) -> list[str]:
        return [str(self.manifest.get("first_month", "")), str(self.manifest.get("last_month", ""))]

    def client(self, client_id: str) -> Client | None:
        return next((item for item in self.clients if item.client_id == client_id), None)

    def months_present(self) -> list[str]:
        """Every month covered by at least one intervention, sorted."""
        return sorted(
            {f"{item.occurred_on.year:04d}-{item.occurred_on.month:02d}" for item in self.interventions}
        )

    def contract_for(self, client_id: str, at_month: str) -> Contract | None:
        """The version in force during ``at_month`` (amendment aware)."""
        last = _month_last(at_month)
        candidates = [
            contract
            for contract in self.contracts
            if contract.client_id == client_id
            and (contract.effective_from is None or contract.effective_from <= last)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda contract: contract.version)


def _month_last(month: str) -> date:
    """Last calendar day of ``2026-09``."""
    return Month.parse(month).last_day()


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _clients(root: Path) -> list[Client]:
    return [
        Client(
            client_id=row["client_id"],
            name=row["name"],
            account_manager_id=row["account_manager_id"],
            sector=row.get("sector", ""),
            onboarded_on=date.fromisoformat(row["onboarded_on"]),
            managed_resource_count=int(row["managed_resource_count"]),
        )
        for row in _read_json(root / "clients.json")
    ]


def _itsm_aliases(root: Path) -> dict[str, str]:
    return {
        row["source_id"]: row["client_id"]
        for row in _read_json(root / "aliases.json")
        if row["source"] == "itsm"
    }


def _billing_aliases(root: Path) -> dict[str, str]:
    return {
        row["source_id"]: row["client_id"]
        for row in _read_json(root / "aliases.json")
        if row["source"] == "billing"
    }


def _invoice_aliases(root: Path) -> dict[str, str]:
    return {
        row["source_id"]: row["client_id"]
        for row in _read_json(root / "aliases.json")
        if row["source"] == "invoice"
    }


def _owner_from_description(description: str, names: dict[str, str]) -> str | None:
    """Which client a reference-less ticket was typed for, if the text says so."""
    lowered = description.lower()
    for name, client_id in names.items():
        if name.lower() in lowered:
            return client_id
    return None


def _interventions(root: Path, dataset: Dataset) -> None:
    aliases = _itsm_aliases(root)
    names = {client.name: client.client_id for client in dataset.clients}
    for row in _read_csv(root / "interventions.csv"):
        reference = row["customer_ref"].strip()
        resolved = aliases.get(reference) if reference else None
        owner = resolved or _owner_from_description(row["description"], names)
        intervention = Intervention(
            intervention_id=row["intervention_id"],
            ticket_id=row["ticket_id"],
            client_id=resolved or UNASSIGNED_CLIENT_ID,
            occurred_on=date.fromisoformat(row["occurred_on"]),
            category=row["category"],
            level=WorkLevel(row["level"]),
            hours_spent=Decimal(row["hours_spent"]),
            description=row["description"],
            ticket_type=row["ticket_type"],
            managed_resource_id=row["managed_resource_id"] or None,
            aws_account_id=row["aws_account_id"] or None,
        )
        dataset.interventions.append(intervention)
        if owner:
            dataset.owners[intervention.intervention_id] = owner


def _contracts(root: Path, dataset: Dataset) -> None:
    expected = _read_json(root / "expected" / "contract_fields.json")
    dataset.expected_fields = list(expected.values())
    for key, row in expected.items():
        text_path = root / "contracts" / f"{key}.txt"
        status = ContractStatus(row["status"])
        contract = extract_contract(text_path, row["client_id"], status)
        contract.effective_from = date.fromisoformat(row["effective_from"])
        dataset.contracts.append(contract)


def _aws_costs(root: Path, dataset: Dataset) -> None:
    aliases = _billing_aliases(root)
    dataset.fx = {row["month"]: Decimal(row["rate"]) for row in _read_csv(root / "fx.csv")}
    for row in _read_csv(root / "aws_costs.csv"):
        month = row["month"]
        rate = dataset.fx[month]
        client_id = aliases.get(row["client_ref"]) if row["client_ref"] else None
        dataset.aws_costs.append(
            AwsCost(
                aws_account_id=row["aws_account_id"],
                month=Month.parse(row["month"]),
                cost=Decimal(row["cost"]) * rate,
                kind=AwsCostKind(row["kind"]),
                client_id=client_id,
                rebilled_amount=Decimal(row["rebilled_amount"]) * rate,
                currency="EUR",
            )
        )


def _invoices(root: Path, dataset: Dataset) -> None:
    aliases = _invoice_aliases(root)
    for row in _read_csv(root / "invoices.csv"):
        client_id = aliases.get(row["customer_ref"])
        if client_id is None:
            continue
        dataset.invoices.append(
            Invoice(
                invoice_id=row["invoice_id"],
                client_id=client_id,
                month=Month.parse(row["month"]),
                kind=InvoiceKind(row["kind"]),
                amount=Decimal(row["amount"]),
                currency=row["currency"],
                hours_billed=Decimal(row["hours_billed"]),
            )
        )


def _costs(root: Path, dataset: Dataset) -> None:
    for row in _read_csv(root / "rates.csv"):
        dataset.rates.append(
            Rate(
                level=WorkLevel(row["level"]),
                hourly_cost=Decimal(row["hourly_cost"]),
                effective_from=date.fromisoformat(row["effective_from"]),
                currency=row["currency"],
            )
        )
    for row in _read_csv(root / "tooling.csv"):
        dataset.tooling.append(
            ToolingCost(
                tool=row["tool"],
                monthly_cost=Decimal(row["monthly_cost"]),
                basis=AllocationBasis(row["basis"]),
                client_id=row["client_id"] or None,
                aws_account_id=row["aws_account_id"] or None,
                currency=row["currency"],
            )
        )
    for row in _read_csv(root / "penalties.csv"):
        dataset.penalties.append(
            Penalty(
                client_id=row["client_id"],
                month=Month.parse(row["month"]),
                amount=Decimal(row["amount"]),
                reason=row["reason"],
                currency=row["currency"],
            )
        )


def load(root: Path) -> Dataset:
    """Load every generated file of ``root`` into domain objects."""
    dataset = Dataset(root=root)
    dataset.clients = _clients(root)
    _interventions(root, dataset)
    _contracts(root, dataset)
    _aws_costs(root, dataset)
    _invoices(root, dataset)
    _costs(root, dataset)
    labels_path = root / "labels" / "interventions.jsonl"
    if labels_path.exists():
        dataset.labels = _read_jsonl(labels_path)
    questions_path = root / "questions" / "reference_questions.json"
    if questions_path.exists():
        dataset.questions = _read_json(questions_path)
    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        dataset.manifest = _read_json(manifest_path)
    return dataset
