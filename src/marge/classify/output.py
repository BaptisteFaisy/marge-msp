"""Annex C structured output: parsing and validation (spec 13.2, Annex C).

``billableHours`` is copied from the recorded duration by code, never produced
by the model (Annex C note). Any output that is not exactly the expected
shape is rejected rather than guessed.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation

from ..domain import Classification, DecisionStatus, Intervention, WorkClass

VALID_CLASSES = {cls.value: cls for cls in WorkClass}
INJECTION_MARKERS = (
    "ignore previous",
    "ignore the above",
    "system:",
    "you are now",
    "nouvelles instructions",
    "oublie les instructions",
)


class InvalidModelOutput(ValueError):
    """Raised when the model output does not match Annex C."""


def extract_json(raw: str) -> dict:
    """Pull the first JSON object out of a model answer."""
    text = (raw or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise InvalidModelOutput("no JSON object in the model answer")
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise InvalidModelOutput(f"invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise InvalidModelOutput("the answer must be a JSON object")
    return payload


def _looks_like_injection(payload: dict) -> bool:
    blob = json.dumps(payload, ensure_ascii=False).lower()
    return any(marker in blob for marker in INJECTION_MARKERS)


def _confidence(payload: dict) -> Decimal:
    try:
        value = Decimal(str(payload.get("confidence", "0")))
    except InvalidOperation as exc:
        raise InvalidModelOutput("confidence is not a number") from exc
    if value < 0 or value > 1:
        raise InvalidModelOutput("confidence outside [0, 1]")
    return value


def _work_class(payload: dict) -> WorkClass:
    raw = str(payload.get("class") or payload.get("workClass") or "").strip().upper()
    if raw not in VALID_CLASSES:
        raise InvalidModelOutput(f"unknown class {raw!r}")
    return VALID_CLASSES[raw]


def parse_model_output(raw: str, intervention: Intervention, contract_version: int = 0) -> Classification:
    """Turn one model answer into an Annex C ``Classification``."""
    payload = extract_json(raw)
    if _looks_like_injection(payload):
        raise InvalidModelOutput("the answer tries to change the task")
    work_class = _work_class(payload)
    return Classification(
        intervention_id=intervention.intervention_id,
        client_id=intervention.client_id or "",
        contract_version=contract_version,
        work_class=work_class,
        confidence=_confidence(payload),
        cited_clause=str(payload.get("citedClause") or "").strip(),
        reason=str(payload.get("reason") or "").strip(),
        billable_hours=intervention.hours_spent,
        status=DecisionStatus.PENDING,
    )


def to_annex_c(classification: Classification) -> dict:
    """Render a classification exactly as Annex C shows it."""
    return {
        "interventionId": classification.intervention_id,
        "customerId": classification.client_id,
        "contractVersion": classification.contract_version,
        "class": classification.work_class.value,
        "confidence": float(classification.confidence),
        "citedClause": classification.cited_clause,
        "reason": classification.reason,
        "billableHours": float(classification.billable_hours),
        "needsHumanValidation": classification.needs_human_validation,
    }
