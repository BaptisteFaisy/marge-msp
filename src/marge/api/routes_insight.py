"""Insight routes: traceability, model-call log and calculation versions.

Three promises of the design, made checkable from the portal:

* ``GET /v1/margins/{client_id}/{month}/why`` — every figure decomposes down to
  its source lines (ENF-TRA-01, idea 37);
* ``GET /v1/llm-calls`` — what was asked of a model, what it cost, what it
  answered, and whether a human then decided otherwise (ENF-IA-01..03, idea 18);
* ``GET /v1/calc-versions`` and ``/diff`` — a change of rate or rule never
  rewrites the past silently (EF-CAL-03, idea 28).

Row-level filtering and cost redaction reuse ``marge.api.rls``: an account
manager sees only their clients and never an hourly cost (ENF-CONF-03).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from ..calc import diff_versions, summarise_diff
from ..domain import Month
from ..llmlog import summarise
from .deps import ApiContext, get_context
from .rls import can_access_client, redact_row

router = APIRouter(prefix="/v1")


def _month_or_404(raw: str) -> Month:
    try:
        return Month.parse(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"month must be YYYY-MM: {raw}") from exc


def _require_access(ctx: ApiContext, client_id: str) -> None:
    if not can_access_client(ctx.actor, client_id, ctx.store.list_clients()):
        raise HTTPException(status_code=403, detail=f"{client_id} is not in your portfolio")


@router.get("/margins/{client_id}/{month}/why")
def margin_why(client_id: str, month: str, ctx: ApiContext = Depends(get_context)) -> dict[str, Any]:
    """The whole chain behind one margin figure, down to the source lines."""
    _require_access(ctx, client_id)
    target = _month_or_404(month)
    rows = ctx.store.list_margin_months(client_id=client_id, month=target)
    if not rows:
        raise HTTPException(status_code=404, detail=f"no margin for {client_id} in {target}")
    latest = max(rows, key=lambda r: r.calc_version)
    lines = ctx.store.margin_lines(client_id, target)
    hours = [h for h in ctx.store.list_hours_summaries(client_id) if h.month == target]

    payload: dict[str, Any] = {
        "client_id": client_id,
        "month": str(target),
        "calc_version": latest.calc_version,
        "state": latest.state.value,
        "revenue_total": str(latest.revenue.total),
        "cost_total": str(latest.costs.total),
        "margin": str(latest.margin),
        "margin_rate": str(latest.margin_rate),
        "coverage_percent": str(latest.coverage.percent),
        "dashboard": f"/dashboards/client/{client_id}?month={target}",
        "posts": _posts(latest),
        "lines": [_line(line, ctx) for line in lines],
        "hours": _hours(hours[0]) if hours else None,
        "versions": [row.calc_version for row in sorted(rows, key=lambda r: r.calc_version)],
    }
    if not latest.incomplete_reason:
        return payload
    payload["incomplete_reason"] = latest.incomplete_reason
    return payload


def _posts(row: Any) -> list[dict[str, str]]:
    """The eight posts of chapter 12, revenue then cost."""
    revenue = (
        ("revenue.subscription", row.revenue.subscription),
        ("revenue.aws_resale", row.revenue.aws_resale_margin),
        ("revenue.extra_hours_billed", row.revenue.extra_hours_billed),
        ("revenue.projects", row.revenue.projects),
    )
    costs = (
        ("cost.labour", row.costs.labour),
        ("cost.tooling", row.costs.tooling),
        ("cost.msp_aws", row.costs.msp_aws),
        ("cost.penalties", row.costs.penalties),
    )
    return [{"post": name, "amount": str(value)} for name, value in (*revenue, *costs)]


def _line(line: Any, ctx: ApiContext) -> dict[str, Any]:
    row = {
        "post": line.post,
        "label": line.label,
        "amount": str(line.amount),
        "source_kind": line.source_kind,
        "source_id": line.source_id,
    }
    return redact_row(row, ctx.actor)


def _hours(summary: Any) -> dict[str, str]:
    return {
        "included_quota": str(summary.included_quota),
        "consumed_hours": str(summary.consumed_hours),
        "out_of_scope_validated_hours": str(summary.out_of_scope_validated_hours),
        "over_quota_hours": str(summary.over_quota_hours),
        "billed_extra_hours": str(summary.billed_extra_hours),
        "unbilled_hours": str(summary.unbilled_hours),
        "unbilled_value": str(summary.unbilled_value),
    }


@router.get("/llm-calls")
def list_llm_calls(
    ctx: ApiContext = Depends(get_context),
    purpose: str | None = None,
    client_id: str | None = None,
    model_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[dict[str, Any]]:
    """The model call log, newest first, filtered by the caller's portfolio."""
    calls = ctx.store.list_llm_calls(purpose=purpose, client_id=client_id, model_id=model_id)
    allowed = {c.client_id for c in ctx.store.list_clients()} & _visible(ctx)
    rows = [c for c in calls if not c.client_id or c.client_id in allowed]
    rows.sort(key=lambda c: c.at, reverse=True)
    return [_call_row(c, ctx) for c in rows[:limit]]


def _visible(ctx: ApiContext) -> set[str]:
    from .rls import visible_client_ids

    return visible_client_ids(ctx.actor, ctx.store.list_clients())


def _call_row(call: Any, ctx: ApiContext) -> dict[str, Any]:
    row = {
        "at": call.at.isoformat(),
        "purpose": call.purpose,
        "model_id": call.model_id,
        "entity_kind": call.entity_kind,
        "entity_id": call.entity_id,
        "client_id": call.client_id,
        "outcome": call.outcome,
        "success": call.success,
        "error": call.error,
        "latency_ms": call.latency_ms,
        "input_tokens": call.input_tokens,
        "output_tokens": call.output_tokens,
        "tokens_estimated": call.tokens_estimated,
        "cost_usd": str(call.cost_usd),
        "injection_detected": call.injection_detected,
        "injection_patterns": list(call.injection_patterns),
    }
    return redact_row(row, ctx.actor)


@router.get("/llm-calls/summary")
def llm_calls_summary(ctx: ApiContext = Depends(get_context), purpose: str | None = None) -> dict[str, Any]:
    """Counts, latency, tokens and estimated cost of the model calls."""
    calls = ctx.store.list_llm_calls(purpose=purpose)
    allowed = _visible(ctx)
    return summarise([c for c in calls if not c.client_id or c.client_id in allowed])


@router.get("/calc-versions")
def list_calc_versions(ctx: ApiContext = Depends(get_context)) -> list[dict[str, Any]]:
    """Every calculation version, with its author, date and reason."""
    _require_controller(ctx)
    return [
        {
            "version": version.version,
            "opened_at": version.opened_at.isoformat(),
            "author": version.author,
            "reason": version.reason,
            "parameters_fingerprint": version.parameters_fingerprint,
        }
        for version in ctx.store.list_calc_versions()
    ]


@router.get("/calc-versions/diff")
def calc_versions_diff(
    ctx: ApiContext = Depends(get_context),
    before: int = Query(ge=1),
    after: int = Query(ge=1),
    month: str | None = None,
) -> dict[str, Any]:
    """What a new calculation version changed, client-month by client-month."""
    _require_controller(ctx)
    target = _month_or_404(month) if month else None
    older = _rows_of_version(ctx, before, target)
    newer = _rows_of_version(ctx, after, target)
    if not older or not newer:
        raise HTTPException(status_code=404, detail=f"no rows for versions {before} and {after}")
    diffs = diff_versions(older, newer)
    payload: dict[str, Any] = {"before": before, "after": after, "summary": summarise_diff(diffs), "rows": []}
    payload["rows"] = [
        {
            "client_id": diff.client_id,
            "month": diff.month,
            "margin_before": str(diff.margin_before),
            "margin_after": str(diff.margin_after),
            "margin_delta": str(diff.margin_delta),
            "rate_delta_points": str(diff.rate_delta_points),
            "changed_posts": list(diff.changed_posts),
        }
        for diff in diffs
    ]
    return payload


def _rows_of_version(ctx: ApiContext, version: int, month: Month | None) -> list[Any]:
    rows = ctx.store.list_margin_months(month=month)
    return [row for row in rows if row.calc_version == version]


def _require_controller(ctx: ApiContext) -> None:
    """Versions and their diff expose hourly costs: management only."""
    if not ctx.actor.sees_hourly_costs:
        raise HTTPException(status_code=403, detail="calculation versions are management only")
