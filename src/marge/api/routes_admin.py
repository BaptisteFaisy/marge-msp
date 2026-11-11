"""Administration and calculation routes (spec 16, EF-ADM-01..02, EF-CAL-03).

Hourly rates and tooling allocation rules are the tunable references a
controller maintains. Reading rates is allowed for every role but the hourly
cost value itself is redacted for account managers (ENF-CONF-03). Mutating
either reference requires a controller/administrator and records an audit line.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from ..calc import compute_coverage
from ..domain import (
    AuditEntry,
    Month,
    Rate,
    ToolingCost,
)
from .deps import ApiContext, get_context
from .recalculate import run_recalculate
from .rls import (
    can_access_client,
    filter_by_clients,
    redact_rates_for_actor,
    visible_client_ids,
)
from .schemas import (
    AllocationRuleUpdateRequest,
    CoverageResponse,
    RateUpdateRequest,
    RecalculateRequest,
    RecalculateResponse,
)
from .serializers import serialize_tooling

router = APIRouter(prefix="/v1")


def _require_settings_role(ctx: ApiContext) -> None:
    if not ctx.actor.manages_settings:
        raise HTTPException(
            status_code=403,
            detail="only the controller or an administrator may change references",
        )


def _parse_decimal(raw: str, field: str) -> Decimal:
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"invalid {field}: {raw!r}") from exc


def _parse_effective_date(raw: str, field: str) -> date:
    try:
        return date.fromisoformat(str(raw))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid {field}: {raw!r}") from exc


@router.get("/rates")
def list_rates(ctx: ApiContext = Depends(get_context)) -> list[dict[str, Any]]:
    """List effective-dated hourly rates, cost redacted for account managers."""
    rates = ctx.store.list_rates()
    return redact_rates_for_actor(rates, ctx.actor)


@router.put("/rates")
def update_rates(
    body: RateUpdateRequest,
    ctx: ApiContext = Depends(get_context),
) -> dict[str, Any]:
    """Append new effective-dated hourly rates (EF-REF-02, EF-VAL-02)."""
    _require_settings_role(ctx)
    new_rates: list[Rate] = []
    for item in body.rates:
        cost = _parse_decimal(item.hourly_cost, "hourly_cost")
        eff = _parse_effective_date(item.effective_from, "effective_from")
        new_rates.append(Rate(level=item.level, hourly_cost=cost, effective_from=eff, currency=item.currency))
    if not new_rates:
        raise HTTPException(status_code=422, detail="at least one rate is required")

    ctx.store.save_rates(new_rates)
    ctx.store.append(
        AuditEntry.now(
            entity_kind="rates",
            entity_id="current",
            action="update_rates",
            author=ctx.actor.actor_id,
            reason=body.reason,
            after={"count": len(new_rates)},
        )
    )
    return {
        "status": "ok",
        "count": len(new_rates),
        "rates": redact_rates_for_actor(ctx.store.list_rates(), ctx.actor),
    }


@router.get("/allocation-rules")
def list_allocation_rules(ctx: ApiContext = Depends(get_context)) -> list[dict[str, Any]]:
    """List tooling allocation rules under client row filtering (EF-REF-03)."""
    clients = ctx.store.list_clients()
    rules = ctx.store.list_tooling_costs()
    visible = filter_by_clients(rules, ctx.actor, clients, client_id_attr="client_id")
    return [serialize_tooling(r) for r in visible]


@router.put("/allocation-rules")
def update_allocation_rules(
    body: AllocationRuleUpdateRequest,
    ctx: ApiContext = Depends(get_context),
) -> dict[str, Any]:
    """Append new tooling allocation rules (EF-REF-03, EF-VAL-02)."""
    _require_settings_role(ctx)
    new_rules: list[ToolingCost] = []
    for item in body.rules:
        cost = _parse_decimal(item.monthly_cost, "monthly_cost")
        new_rules.append(
            ToolingCost(
                tool=item.tool,
                monthly_cost=cost,
                basis=item.basis,
                client_id=item.client_id,
                aws_account_id=item.aws_account_id,
                currency=item.currency,
            )
        )
    if not new_rules:
        raise HTTPException(status_code=422, detail="at least one rule is required")

    ctx.store.save_tooling_costs(new_rules)
    ctx.store.append(
        AuditEntry.now(
            entity_kind="allocation_rules",
            entity_id="current",
            action="update_allocation_rules",
            author=ctx.actor.actor_id,
            reason=body.reason,
            after={"count": len(new_rules)},
        )
    )
    return {"status": "ok", "count": len(new_rules)}


@router.get("/coverage", response_model=CoverageResponse)
def get_coverage(
    month: str | None = Query(default=None),
    ctx: ApiContext = Depends(get_context),
) -> dict[str, Any]:
    """Data coverage indicator scoped to the actor's visible rows (EF-ADM-02)."""
    parsed_month = None
    if month is not None:
        try:
            parsed_month = Month.parse(month)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    allowed = visible_client_ids(ctx.actor, ctx.store.list_clients())
    interventions = ctx.store.list_interventions(month=parsed_month)
    scoped = [iv for iv in interventions if iv.client_id is None or iv.client_id in allowed]
    coverage = compute_coverage(scoped)
    floor_percent = ctx.settings.coverage_floor * 100
    return {
        "total_hours": str(coverage.total_hours),
        "attributed_hours": str(coverage.attributed_hours),
        "coverage_ratio": str(coverage.value),
        "coverage_percent": str(coverage.percent),
        "floor_percent": str(floor_percent),
        "healthy": coverage.value >= ctx.settings.coverage_floor,
    }


@router.post("/recalculate", response_model=RecalculateResponse)
def recalculate(
    body: RecalculateRequest,
    ctx: ApiContext = Depends(get_context),
) -> dict[str, Any]:
    """Recompute margins for a month via ``marge.calc`` (EF-CAL-01..03)."""
    if ctx.actor.is_account_manager:
        raise HTTPException(status_code=403, detail="account managers cannot trigger a recalculation")
    if body.client_id is not None:
        clients = ctx.store.list_clients()
        if not can_access_client(ctx.actor, body.client_id, clients):
            raise HTTPException(status_code=403, detail="access denied for this client")

    try:
        Month.parse(body.month)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid month: {exc}") from exc

    count, calc_version = run_recalculate(
        store=ctx.store,
        settings=ctx.settings,
        actor=ctx.actor,
        month_str=body.month,
        client_id=body.client_id,
        reason=body.reason,
    )
    return {
        "status": "ok",
        "month": body.month,
        "calculated_clients": count,
        "calc_version": calc_version,
        "reasons": [],
    }
