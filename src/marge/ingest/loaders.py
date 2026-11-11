"""Monthly load orchestration: read the sources, write the store (spec 8.1).

One function per load, one report per load, so the nightly run and the CLI
share exactly the same code.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from ..domain import Client, ClientMatch, Month, Rate, ToolingCost, WorkLevel
from ..match import Alias, ClientName, MappingResolver, propose_matches
from ..pipeline.reports import LoadReport
from ..store.base import Store
from .billing import load_aws_costs, parse_fx
from .invoices import to_invoice
from .tickets import load_interventions, read_csv


@dataclass(slots=True)
class SourceFiles:
    """Where the export files live (docs/DATA-FORMATS.md)."""

    root: Path
    clients: Path | None = None
    aliases: Path | None = None
    interventions: Path | None = None
    aws_costs: Path | None = None
    fx: Path | None = None
    invoices: Path | None = None
    rates: Path | None = None
    tooling: Path | None = None
    extra: dict[str, Path] = field(default_factory=dict)

    @classmethod
    def of(cls, root: str | Path) -> SourceFiles:
        base = Path(root)
        return cls(
            root=base,
            clients=base / "clients.json",
            aliases=base / "aliases.json",
            interventions=base / "interventions.csv",
            aws_costs=base / "aws_costs.csv",
            fx=base / "fx.csv",
            invoices=base / "invoices.csv",
            rates=base / "rates.csv",
            tooling=base / "tooling.csv",
        )


def read_json(path: Path | None) -> list[dict]:
    if path is None or not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def load_clients(store: Store, path: Path | None) -> int:
    rows = read_json(path)
    clients = [
        Client(
            client_id=row["client_id"],
            name=row["name"],
            account_manager_id=row.get("account_manager_id", ""),
            sector=row.get("sector", ""),
            managed_resource_count=int(row.get("managed_resource_count", 0)),
        )
        for row in rows
    ]
    return store.upsert_clients(clients)


def load_aliases(path: Path | None) -> list[Alias]:
    from ..domain import SourceKind

    return [
        Alias(
            client_id=row["client_id"],
            source=SourceKind(row["source"]),
            source_id=row["source_id"],
            name_variant=row.get("name_variant", row["source_id"]),
        )
        for row in read_json(path)
    ]


def load_rates(store: Store, path: Path | None) -> int:
    from datetime import date

    rows = read_csv(read_text(path))
    rates = [
        Rate(
            level=WorkLevel(row["level"]),
            hourly_cost=Decimal(str(row["hourly_cost"])),
            effective_from=date.fromisoformat(row["effective_from"]),
            currency=row.get("currency", "EUR"),
        )
        for row in rows
    ]
    return store.save_rates(rates) if rates else 0


def load_tooling(store: Store, path: Path | None) -> int:
    from ..domain import AllocationBasis

    rows = read_csv(read_text(path))
    costs = [
        ToolingCost(
            tool=row["tool"],
            monthly_cost=Decimal(str(row["monthly_cost"])),
            basis=AllocationBasis(row.get("basis") or "PER_LABOUR_HOUR"),
            client_id=(row.get("client_id") or None),
            aws_account_id=(row.get("aws_account_id") or None),
            currency=row.get("currency", "EUR"),
        )
        for row in rows
    ]
    return store.save_tooling_costs(costs) if costs else 0


def propose_and_save_matches(store: Store, aliases: list[Alias]) -> int:
    clients = [ClientName(c.client_id, c.name) for c in store.list_clients()]
    proposals: list[ClientMatch] = propose_matches(aliases, clients, store.load())
    return store.save_matches(proposals) if proposals else 0


def resolver_for(store: Store, aliases: Iterable[Alias]) -> MappingResolver:
    return MappingResolver(list(aliases), store.list_matches())


def load_month(store: Store, files: SourceFiles, month: Month) -> list[LoadReport]:
    """Load one month from the export files into the store."""
    aliases = load_aliases(files.aliases)
    resolver = resolver_for(store, aliases)
    reports: list[LoadReport] = []

    rows = read_csv(read_text(files.interventions))
    interventions = list(load_interventions(rows, resolver))
    month_rows = [i for i in interventions if i.month == month]
    store.save_interventions(month_rows)
    unattributed = sum((i.hours_spent for i in month_rows if not i.attributed), Decimal("0"))
    reports.append(
        LoadReport(
            source="itsm",
            month=month,
            rows=len(month_rows),
            resolved=sum(1 for i in month_rows if i.attributed),
            unresolved=sum(1 for i in month_rows if not i.attributed),
            unattributed_hours=unattributed,
        )
    )

    fx = parse_fx(read_csv(read_text(files.fx)))
    aws_rows = [r for r in read_csv(read_text(files.aws_costs)) if r.get("month") == str(month)]
    costs = list(load_aws_costs(aws_rows, resolver, fx))
    store.save_aws_costs(costs)
    reports.append(LoadReport(source="billing", month=month, rows=len(costs), resolved=len(costs)))

    invoice_rows = [r for r in read_csv(read_text(files.invoices)) if r.get("month") == str(month)]
    invoices = [i for i in (to_invoice(r, resolver) for r in invoice_rows) if i is not None]
    store.save_invoices(invoices)
    reports.append(
        LoadReport(
            source="invoice",
            month=month,
            rows=len(invoice_rows),
            resolved=len(invoices),
            unresolved=len(invoice_rows) - len(invoices),
        )
    )
    return reports


def load_reference_data(store: Store, files: SourceFiles) -> dict[str, int]:
    """Clients, aliases, rates, tooling, then the match proposals."""
    aliases = load_aliases(files.aliases)
    return {
        "clients": load_clients(store, files.clients),
        "aliases": len(aliases),
        "rates": load_rates(store, files.rates),
        "tooling": load_tooling(store, files.tooling),
        "matches": propose_and_save_matches(store, aliases),
    }
