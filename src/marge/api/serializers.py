"""JSON-safe serialization and field patching helpers for the API (spec 16).

Every ``Decimal`` is converted to ``str`` and every ``date``/``datetime`` to ISO
8601 text so FastAPI always emits deterministic JSON without float rounding.
Amounts are normalised (cents) and durations (hundredths) on the way out.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from ..domain import (
    Classification,
    ClientMatch,
    Contract,
    ContractFields,
    Intervention,
    SourceSpan,
    ToolingCost,
    hours,
    money,
)


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _str_or_none(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def serialize_match(match: ClientMatch) -> dict[str, Any]:
    return {
        "match_id": match.match_id,
        "client_id": match.client_id,
        "source": match.source.value,
        "source_id": match.source_id,
        "confidence": str(match.confidence),
        "status": match.status.value,
        "decided_by": match.decided_by,
        "decided_at": _iso(match.decided_at),
        "reason": match.reason,
    }


def serialize_classification(
    cls: Classification,
    intervention: Intervention | None = None,
) -> dict[str, Any]:
    return {
        "intervention_id": cls.intervention_id,
        "client_id": cls.client_id,
        "contract_version": cls.contract_version,
        "work_class": cls.work_class.value,
        "confidence": str(cls.confidence),
        "cited_clause": cls.cited_clause,
        "reason": cls.reason,
        "billable_hours": str(cls.billable_hours),
        "status": cls.status.value,
        "needs_human_validation": cls.needs_human_validation,
        "ticket_id": intervention.ticket_id if intervention else None,
        "occurred_on": _iso(intervention.occurred_on) if intervention else None,
        "category": intervention.category if intervention else None,
        "level": intervention.level.value if intervention else None,
        "description": intervention.description if intervention else None,
    }


def serialize_tooling(cost: ToolingCost) -> dict[str, Any]:
    return {
        "tool": cost.tool,
        "monthly_cost": str(money(cost.monthly_cost)),
        "basis": cost.basis.value,
        "client_id": cost.client_id,
        "aws_account_id": cost.aws_account_id,
        "currency": cost.currency,
    }


def serialize_margin(row: Any, client_name: str = "") -> dict[str, Any]:
    """One row of ``marge_client_mois`` (EF-CAL-01, Annex A, EF-TDB-01).

    Amounts stay strings so no float rounds a figure on the way out. The
    per-post decomposition and the source lines live on
    ``/v1/margins/{client_id}/{month}/why`` (ENF-TRA-01).
    """
    return {
        "client_id": row.client_id,
        "client_name": client_name,
        "account_manager_id": row.account_manager_id,
        "month": str(row.month),
        "revenue_total": str(row.revenue.total),
        "cost_total": str(row.costs.total),
        "margin": str(row.margin),
        "margin_rate": str(row.margin_rate),
        "margin_rate_percent": str((row.margin_rate * 100).quantize(Decimal("0.1"))),
        "coverage_percent": str(row.coverage.percent),
        "state": row.state.value,
        "is_estimate": row.is_estimate,
        "calc_version": row.calc_version,
        "incomplete_reason": row.incomplete_reason,
        "why": f"/v1/margins/{row.client_id}/{row.month}/why",
    }


def _serialize_spans(spans: dict[str, SourceSpan]) -> dict[str, dict[str, Any]]:
    return {
        name: {
            "quote": span.quote,
            "page": span.page,
            "char_start": span.char_start,
            "char_end": span.char_end,
        }
        for name, span in spans.items()
    }


def serialize_fields(fields: ContractFields) -> dict[str, Any]:
    """Every Annex B field, each with its source span (EF-CTR-02)."""
    return {
        "customer_name": fields.customer_name,
        "start_date": _iso(fields.start_date),
        "end_date": _iso(fields.end_date),
        "renewal_terms": fields.renewal_terms,
        "termination_notice": fields.termination_notice,
        "monthly_subscription": str(money(fields.monthly_subscription)),
        "currency": fields.currency,
        "included_hours_per_month": (
            str(hours(fields.included_hours_per_month))
            if fields.included_hours_per_month is not None
            else None
        ),
        "extra_hour_rate": str(money(fields.extra_hour_rate)),
        "services_included": list(fields.services_included),
        "exclusions": list(fields.exclusions),
        "service_hours": fields.service_hours,
        "penalties": fields.penalties,
        "indexation_clause": fields.indexation_clause,
        "covered_accounts_or_resources": fields.covered_accounts_or_resources,
        "spans": _serialize_spans(fields.spans),
    }


def serialize_contract_snapshot(contract: Contract) -> dict[str, Any]:
    """Compact contract state used as ``before``/``after`` in the audit log."""
    fields = serialize_fields(contract.fields)
    return {
        "status": contract.status.value,
        "monthly_subscription": fields["monthly_subscription"],
        "included_hours_per_month": fields["included_hours_per_month"],
        "extra_hour_rate": fields["extra_hour_rate"],
    }


def serialize_contract(contract: Contract) -> dict[str, Any]:
    return {
        "contract_id": contract.contract_id,
        "client_id": contract.client_id,
        "version": contract.version,
        "status": contract.status.value,
        "document_key": contract.document_key,
        "effective_from": _iso(contract.effective_from),
        "validated_by": contract.validated_by,
        "validated_at": _iso(contract.validated_at),
        "validation_reason": contract.validation_reason,
        "fields": serialize_fields(contract.fields),
    }


def _parse_date_opt(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _parse_spans(raw: Any) -> dict[str, SourceSpan]:
    if not isinstance(raw, dict):
        return {}
    parsed: dict[str, SourceSpan] = {}
    for key, val in raw.items():
        if isinstance(val, dict) and "quote" in val:
            parsed[str(key)] = SourceSpan(
                quote=str(val["quote"]),
                page=val.get("page"),
                char_start=val.get("char_start"),
                char_end=val.get("char_end"),
            )
    return parsed


TEXT_FIELD_KEYS = (
    "customer_name",
    "renewal_terms",
    "termination_notice",
    "currency",
    "service_hours",
    "penalties",
    "indexation_clause",
)


def _apply_text_fields(fields: ContractFields, updates: dict[str, Any]) -> None:
    for key in TEXT_FIELD_KEYS:
        if key in updates and updates[key] is not None:
            setattr(fields, key, str(updates[key]))


def _apply_amount_fields(fields: ContractFields, updates: dict[str, Any]) -> None:
    if updates.get("monthly_subscription") is not None:
        fields.monthly_subscription = money(Decimal(str(updates["monthly_subscription"])))
    if updates.get("extra_hour_rate") is not None:
        fields.extra_hour_rate = money(Decimal(str(updates["extra_hour_rate"])))
    if "included_hours_per_month" in updates:
        raw_inc = updates["included_hours_per_month"]
        fields.included_hours_per_month = None if raw_inc is None else hours(Decimal(str(raw_inc)))


def _apply_collection_fields(fields: ContractFields, updates: dict[str, Any]) -> None:
    if isinstance(updates.get("services_included"), list):
        fields.services_included = tuple(str(x) for x in updates["services_included"])
    if isinstance(updates.get("exclusions"), list):
        fields.exclusions = tuple(str(x) for x in updates["exclusions"])
    if "covered_accounts_or_resources" in updates:
        val = updates["covered_accounts_or_resources"]
        fields.covered_accounts_or_resources = None if val is None else int(val)
    if "spans" in updates:
        fields.spans.update(_parse_spans(updates["spans"]))


def apply_field_updates(fields: ContractFields, updates: dict[str, Any]) -> None:
    """Apply validated field edits onto ``ContractFields`` in place."""
    _apply_text_fields(fields, updates)
    if "start_date" in updates:
        fields.start_date = _parse_date_opt(updates["start_date"])
    if "end_date" in updates:
        fields.end_date = _parse_date_opt(updates["end_date"])
    _apply_amount_fields(fields, updates)
    _apply_collection_fields(fields, updates)
    fields.normalise_amounts()
