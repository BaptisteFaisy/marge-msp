"""Clients, identity matches and contracts (spec 9.1, 9.2, Annex B).

Domain layer: standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .enums import ContractStatus, DecisionStatus, SourceKind
from .money import hours, money


@dataclass(frozen=True, slots=True)
class Client:
    """A customer of the MSP, keyed by its common identifier."""

    client_id: str
    name: str
    account_manager_id: str
    sector: str = ""
    onboarded_on: date | None = None
    managed_resource_count: int = 0


@dataclass(slots=True)
class ClientMatch:
    """Proposed link between the common id and one source id (EF-REF-01).

    The model proposes, a human validates: ``status`` starts as PENDING and the
    match is unusable for the calculation until APPROVED.
    """

    match_id: str
    client_id: str
    source: SourceKind
    source_id: str
    confidence: Decimal
    status: DecisionStatus = DecisionStatus.PENDING
    decided_by: str | None = None
    decided_at: date | None = None
    reason: str = ""

    @property
    def usable(self) -> bool:
        return self.status == DecisionStatus.APPROVED


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """Where an extracted value was read in the contract (EF-CTR-02)."""

    quote: str
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None


@dataclass(frozen=True, slots=True)
class ExtractedField:
    """One Annex B field: its value plus the passage it comes from."""

    name: str
    value: str
    span: SourceSpan | None = None
    confidence: Decimal = Decimal("0")
    corrected: bool = False


@dataclass(frozen=True, slots=True)
class SlaCommitment:
    """A service level commitment and its penalty."""

    subject: str
    target: str
    penalty_rule: str = ""


@dataclass(slots=True)
class ContractFields:
    """Annex B — every field extracted from one contract.

    ``services_included`` and ``exclusions`` are kept whole: they drive the
    classification of interventions (spec 13.1).
    """

    customer_name: str = ""
    start_date: date | None = None
    end_date: date | None = None
    renewal_terms: str = ""
    termination_notice: str = ""
    monthly_subscription: Decimal = Decimal("0")
    currency: str = "EUR"
    included_hours_per_month: Decimal | None = None
    extra_hour_rate: Decimal = Decimal("0")
    services_included: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = ()
    service_hours: str = ""
    sla_commitments: tuple[SlaCommitment, ...] = ()
    penalties: str = ""
    indexation_clause: str = ""
    covered_accounts_or_resources: int | None = None
    spans: dict[str, SourceSpan] = field(default_factory=dict)

    def normalise_amounts(self) -> None:
        self.monthly_subscription = money(self.monthly_subscription)
        self.extra_hour_rate = money(self.extra_hour_rate)
        if self.included_hours_per_month is not None:
            self.included_hours_per_month = hours(self.included_hours_per_month)

    def scope_text(self) -> str:
        """Full in-scope/out-of-scope text handed to the classifier."""
        included = "\n".join(f"- {item}" for item in self.services_included)
        excluded = "\n".join(f"- {item}" for item in self.exclusions)
        return f"INCLUDED SERVICES:\n{included}\n\nEXCLUSIONS:\n{excluded}"


@dataclass(slots=True)
class Contract:
    """One version of one contract. An amendment creates a new version."""

    contract_id: str
    client_id: str
    version: int
    fields: ContractFields
    status: ContractStatus = ContractStatus.RECEIVED
    document_key: str = ""
    effective_from: date | None = None
    validated_by: str | None = None
    validated_at: date | None = None
    validation_reason: str = ""

    @property
    def counts_for_calculation(self) -> bool:
        return self.status == ContractStatus.VALIDATED
