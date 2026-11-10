"""Enumerations shared by every Marge module.

Domain layer: standard library only. Never import boto3, fastapi or pydantic
here (see docs/CONTRACT.md).
"""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):  # noqa: UP042 - str mixin keeps JSON/SQL values stable
    """String enum with a stable ``value`` used in JSON, SQL and prompts."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return str(self.value)


class SourceKind(StrEnum):
    """Where a raw record comes from (spec 9.1, EF-SRC-01..04)."""

    ITSM = "itsm"
    BILLING = "billing"
    CONTRACT = "contract"
    INVOICE = "invoice"


class WorkLevel(StrEnum):
    """Skill level. People are never stored, only levels (ENF-CONF-01)."""

    N1 = "N1"
    N2 = "N2"
    N3 = "N3"
    ARCHITECT = "ARCHITECT"


class WorkClass(StrEnum):
    """Outcome of classifying an intervention (spec 13.2, Annex C)."""

    INCLUDED = "IN_SCOPE"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    UNCERTAIN = "UNCERTAIN"


class DecisionStatus(StrEnum):
    """Human decision on a model proposal (ENF-IA-02)."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    CORRECTED = "CORRECTED"
    REJECTED = "REJECTED"


class ContractStatus(StrEnum):
    """A contract only feeds the calculation once VALIDATED (EF-CTR-03)."""

    RECEIVED = "RECEIVED"
    EXTRACTED = "EXTRACTED"
    VALIDATED = "VALIDATED"
    AMENDED = "AMENDED"
    SUPERSEDED = "SUPERSEDED"


class AllocationBasis(StrEnum):
    """Tooling cost allocation rule (EF-REF-03, spec 12.2)."""

    PER_CLIENT = "PER_CLIENT"
    PER_ACCOUNT = "PER_ACCOUNT"
    PER_MANAGED_RESOURCE = "PER_MANAGED_RESOURCE"
    PER_LABOUR_HOUR = "PER_LABOUR_HOUR"


class AwsCostKind(StrEnum):
    """Client account cost versus MSP-owned tooling account cost."""

    CLIENT_ACCOUNT = "CLIENT_ACCOUNT"
    MSP_TOOLING_ACCOUNT = "MSP_TOOLING_ACCOUNT"


class InvoiceKind(StrEnum):
    """Revenue lines coming from issued invoices (spec 12.1)."""

    EXTRA_HOURS = "EXTRA_HOURS"
    PROJECT = "PROJECT"
    SUBSCRIPTION = "SUBSCRIPTION"


class MarginState(StrEnum):
    """Displayed state of a monthly margin (spec 12.4)."""

    COMPLETE = "COMPLETE"
    ESTIMATE = "ESTIMATE"
    INCOMPLETE = "INCOMPLETE"


class UnbilledState(StrEnum):
    """State of detected unbilled hours (EF-TDB-03)."""

    DETECTED = "DETECTED"
    VALIDATED = "VALIDATED"
    BILLED = "BILLED"
    WRITTEN_OFF = "WRITTEN_OFF"


class ActorRole(StrEnum):
    """Portal roles (spec 6)."""

    EXECUTIVE = "EXECUTIVE"
    OPERATIONS_DIRECTOR = "OPERATIONS_DIRECTOR"
    ACCOUNT_MANAGER = "ACCOUNT_MANAGER"
    CONTROLLER = "CONTROLLER"
    ADMINISTRATOR = "ADMINISTRATOR"


UNASSIGNED_CLIENT_ID = "UNASSIGNED"
"""Pseudo client id for hours that could not be attached (spec 12.4)."""
