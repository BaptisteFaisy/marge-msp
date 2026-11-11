"""Contract reading and validation (spec 9.2, 13.1)."""

from __future__ import annotations

from .data_automation import BedrockDataAutomation, DataAutomationError
from .extraction import LocalTextExtractor, extract_fields, side_by_side
from .schema import (
    FIELD_HINTS,
    FIELD_PLAN,
    FieldPlanEntry,
    field_plan_payload,
    to_contract_fields,
    validate_fields,
)
from .validation import (
    ContractNotUsable,
    awaiting_validation,
    mark_extracted,
    new_version,
    validate_contract,
)

__all__ = [
    "FIELD_HINTS",
    "FIELD_PLAN",
    "BedrockDataAutomation",
    "ContractNotUsable",
    "DataAutomationError",
    "FieldPlanEntry",
    "LocalTextExtractor",
    "awaiting_validation",
    "extract_fields",
    "field_plan_payload",
    "mark_extracted",
    "new_version",
    "side_by_side",
    "to_contract_fields",
    "validate_contract",
    "validate_fields",
]
