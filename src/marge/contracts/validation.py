"""Contract validation and versioning (EF-CTR-02..04, ENF-IA-02).

A contract only feeds the calculation once a human validated it: an extracted
contract has no effect on any margin (spec 12.4, R4).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ..domain import Contract, ContractFields, ContractStatus
from .schema import validate_fields


class ContractNotUsable(ValueError):
    """Raised when a contract cannot be validated (blocking field problem)."""


def validate_contract(
    contract: Contract,
    author: str,
    reason: str = "",
    corrections: dict[str, Any] | None = None,
    today: date | None = None,
) -> Contract:
    """Approve a contract after human review, applying any correction first."""
    fields = _apply_corrections(contract.fields, corrections or {})
    problems = validate_fields(fields)
    if problems:
        raise ContractNotUsable("; ".join(problems))
    contract.fields = fields
    contract.status = ContractStatus.VALIDATED
    contract.validated_by = author
    contract.validated_at = today or date.today()
    contract.validation_reason = reason or "validated in the portal"
    contract.effective_from = contract.effective_from or fields.start_date
    return contract


def _apply_corrections(fields: ContractFields, corrections: dict[str, Any]) -> ContractFields:
    for name, value in corrections.items():
        if not hasattr(fields, name):
            continue
        if name in ("monthly_subscription", "extra_hour_rate", "included_hours_per_month"):
            setattr(fields, name, None if value in (None, "") else value)
        elif name in ("services_included", "exclusions"):
            setattr(fields, name, tuple(value) if not isinstance(value, str) else tuple(value.splitlines()))
        else:
            setattr(fields, name, value)
    fields.normalise_amounts()
    return fields


def new_version(
    previous: Contract,
    fields: ContractFields,
    author: str,  # noqa: ARG001 - kept for the audit trail of the caller
    reason: str,
    today: date | None = None,
) -> Contract:
    """EF-CTR-04 — an amendment creates a new dated version, it never rewrites.

    The author is recorded by the caller in the audit log, which is why the
    parameter is part of the signature but not used here.
    """
    previous.status = ContractStatus.SUPERSEDED
    return Contract(
        contract_id=previous.contract_id,
        client_id=previous.client_id,
        version=previous.version + 1,
        fields=fields,
        status=ContractStatus.EXTRACTED,
        document_key=previous.document_key.replace(f"-v{previous.version}", f"-v{previous.version + 1}"),
        effective_from=today or date.today(),
        validation_reason=reason,
    )


def mark_extracted(contract: Contract) -> Contract:
    """The extraction step ran; the contract now waits for a human."""
    contract.status = ContractStatus.EXTRACTED
    return contract


def awaiting_validation(contracts: list[Contract]) -> list[Contract]:
    return [c for c in contracts if c.status in (ContractStatus.RECEIVED, ContractStatus.EXTRACTED)]
