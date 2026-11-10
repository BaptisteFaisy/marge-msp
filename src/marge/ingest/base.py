"""Connector interfaces (spec 7 — replaceable connectors).

Another MSP plugs its own ITSM tool by writing one adapter. The reference
implementation reads CSV/JSON exports; the AWS implementation reads S3.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Protocol

from ..domain import AwsCost, Contract, Intervention, Invoice, Month


class TicketSource(Protocol):
    """EF-SRC-01 — tickets and the time spent on them."""

    def fetch_interventions(self, month: Month) -> Iterator[Intervention]: ...


class BillingSource(Protocol):
    """EF-SRC-02 — AWS cost per account per month."""

    def fetch_aws_costs(self, month: Month) -> Iterator[AwsCost]: ...


class InvoiceSource(Protocol):
    """EF-SRC-04 — invoices issued to clients (optional)."""

    def fetch_invoices(self, month: Month) -> Iterator[Invoice]: ...


class ContractSource(Protocol):
    """EF-SRC-03 — contract documents, read from a bucket."""

    def list_documents(self) -> Sequence[str]: ...
    def read_document(self, key: str) -> bytes: ...
    def fetch_contracts(self) -> Iterator[Contract]: ...


class DocumentExtractor(Protocol):
    """Reads Annex B fields out of a contract document.

    Implemented by ``marge.contracts.extraction`` on top of Bedrock Data
    Automation, and by a deterministic local extractor used in tests and in
    the offline demo.
    """

    def extract(self, document_key: str, content: bytes) -> Contract: ...


class WorkClassifier(Protocol):
    """Classifies one intervention against the scope of a contract.

    Implemented on top of a Bedrock model (Annex C output) and by a rule-based
    local classifier for tests.
    """

    def classify(self, intervention: Intervention, contract: Contract) -> object: ...


class ItsmActions(Protocol):
    """Write side of the ticket tool, used by the MCP server (spec 14.3)."""

    def create_renegotiation_task(self, client_id: str, owner_id: str, dossier: str) -> str: ...
    def open_task_exists(self, client_id: str, kind: str) -> bool: ...
    def store_billing_draft(self, client_id: str, proposal: str) -> str: ...
