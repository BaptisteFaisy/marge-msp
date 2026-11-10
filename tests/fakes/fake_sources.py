"""Source doubles (spec 7 — replaceable connectors)."""

from __future__ import annotations

from collections.abc import Iterator, Sequence

from marge.domain import AwsCost, Contract, Intervention, Invoice, Month


class ListTicketSource:
    """A ticket source backed by an in-memory list."""

    def __init__(self, interventions: Sequence[Intervention]) -> None:
        self._rows = list(interventions)
        self.calls: list[Month] = []

    def fetch_interventions(self, month: Month) -> Iterator[Intervention]:
        self.calls.append(month)
        yield from (i for i in self._rows if i.month == month)


class ListBillingSource:
    def __init__(self, costs: Sequence[AwsCost]) -> None:
        self._rows = list(costs)

    def fetch_aws_costs(self, month: Month) -> Iterator[AwsCost]:
        yield from (c for c in self._rows if c.month == month)


class ListInvoiceSource:
    def __init__(self, invoices: Sequence[Invoice]) -> None:
        self._rows = list(invoices)

    def fetch_invoices(self, month: Month) -> Iterator[Invoice]:
        yield from (i for i in self._rows if i.month == month)


class DictContractSource:
    """A contract source backed by a ``{key: bytes}`` mapping."""

    def __init__(self, documents: dict[str, bytes], contracts: Sequence[Contract] = ()) -> None:
        self._documents = dict(documents)
        self._contracts = list(contracts)

    def list_documents(self) -> Sequence[str]:
        return sorted(self._documents)

    def read_document(self, key: str) -> bytes:
        return self._documents[key]

    def fetch_contracts(self) -> Iterator[Contract]:
        yield from self._contracts
