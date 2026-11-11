"""Pydantic request/response schemas for the portal API (spec 16).

Request models validate every input (EF-VAL-02 requires a non-empty audit
reason on each decision). Amounts and dates travel as strings so no float ever
touches a monetary value. Response payloads are built by ``serializers`` and
checked by the ``*Response`` models used on the routes.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..domain import AllocationBasis, DecisionStatus, WorkLevel


class DecisionRequest(BaseModel):
    """Payload for human validation/rejection of a proposal (EF-VAL-02)."""

    decision: DecisionStatus
    reason: str = Field(..., min_length=1, description="Audit reason for the human decision")
    corrected_value: dict[str, Any] | None = None


class ContractValidateRequest(BaseModel):
    """Payload to validate a contract (EF-CTR-03, EF-VAL-02)."""

    reason: str = Field(..., min_length=1, description="Audit justification for contract validation")
    corrections: dict[str, Any] | None = None


class ContractFieldsUpdateRequest(BaseModel):
    """Payload to correct extracted contract fields (EF-CTR-02)."""

    reason: str = Field(..., min_length=1, description="Reason for field modification")
    fields: dict[str, Any]


class RateItem(BaseModel):
    """Loaded hourly cost for one skill level (EF-REF-02)."""

    level: WorkLevel
    hourly_cost: str
    effective_from: str
    currency: str = "EUR"


class RateUpdateRequest(BaseModel):
    """Payload to append hourly rates (EF-REF-02, EF-VAL-02)."""

    reason: str = Field(..., min_length=1, description="Justification for rate update")
    rates: list[RateItem]


class AllocationRuleItem(BaseModel):
    """A tooling cost allocation rule (EF-REF-03)."""

    tool: str
    monthly_cost: str
    basis: AllocationBasis
    client_id: str | None = None
    aws_account_id: str | None = None
    currency: str = "EUR"


class AllocationRuleUpdateRequest(BaseModel):
    """Payload to append tooling allocation rules (EF-REF-03, EF-VAL-02)."""

    reason: str = Field(..., min_length=1, description="Justification for rule update")
    rules: list[AllocationRuleItem]


class RecalculateRequest(BaseModel):
    """Request to recompute the margin of a month (EF-CAL-03)."""

    month: str = Field(..., description="Month to recompute, YYYY-MM")
    client_id: str | None = Field(default=None, description="Optional single-client filter")
    reason: str = Field(default="on-demand recalculation", description="Audit reason")


class RecalculateResponse(BaseModel):
    """Summary of one recalculation run."""

    status: str
    month: str
    calculated_clients: int
    calc_version: int
    reasons: list[str] = Field(default_factory=list)


class CoverageResponse(BaseModel):
    """Data coverage indicator (EF-ADM-02)."""

    total_hours: str
    attributed_hours: str
    coverage_ratio: str
    coverage_percent: str
    floor_percent: str
    healthy: bool
