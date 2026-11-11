"""Validation routes: matches, contracts, and classifications (spec 16).

Every human decision records an ``AuditEntry`` with author, timestamp and
reason (EF-VAL-02). Row-level access is checked on every client-scoped entity
(EF-TDB-06).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from ..domain import (
    AuditEntry,
    CategoryDecision,
    Classification,
    ContractStatus,
    DecisionStatus,
    Month,
    WorkClass,
)
from .deps import ApiContext, get_context
from .rls import can_access_client, filter_by_clients, redact_contract_for_actor
from .schemas import (
    ContractFieldsUpdateRequest,
    ContractValidateRequest,
    DecisionRequest,
)
from .serializers import (
    apply_field_updates,
    serialize_classification,
    serialize_contract_snapshot,
    serialize_match,
)

router = APIRouter(prefix="/v1")


def _require_client_access(ctx: ApiContext, client_id: str) -> None:
    clients = ctx.store.list_clients()
    if not can_access_client(ctx.actor, client_id, clients):
        raise HTTPException(status_code=403, detail="access denied for this client")


def _apply_match_correction(ctx: ApiContext, match, body: DecisionRequest) -> None:
    """Move a match to the corrected client id, checking the new client too."""
    if body.decision != DecisionStatus.CORRECTED or not body.corrected_value:
        return
    new_cid = body.corrected_value.get("client_id")
    if new_cid is None:
        return
    new_cid = str(new_cid)
    _require_client_access(ctx, new_cid)
    match.client_id = new_cid


def _apply_work_class_correction(cls: Classification, body: DecisionRequest) -> None:
    """Override the proposed work class on a corrected classification."""
    if body.decision != DecisionStatus.CORRECTED or not body.corrected_value:
        return
    raw = body.corrected_value.get("work_class")
    if raw is None:
        return
    try:
        cls.work_class = WorkClass(str(raw))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid work_class: {exc}") from exc


def _find_classification(ctx: ApiContext, intervention_id: str) -> Classification | None:
    for cls in ctx.store.list_classifications():
        if cls.intervention_id == intervention_id:
            return cls
    return None


@router.get("/matches")
def list_matches(
    pending_only: bool = Query(default=False),
    ctx: ApiContext = Depends(get_context),
) -> list[dict[str, Any]]:
    """List proposed client matches filtered by actor visibility (EF-REF-01)."""
    clients = ctx.store.list_clients()
    matches = ctx.store.list_matches(pending_only=pending_only)
    visible = filter_by_clients(matches, ctx.actor, clients)
    return [serialize_match(m) for m in visible]


@router.post("/matches/{match_id}/decision")
def decide_match(
    match_id: str,
    body: DecisionRequest,
    ctx: ApiContext = Depends(get_context),
) -> dict[str, Any]:
    """Approve, correct or reject a proposed client match (EF-REF-01, EF-VAL-02)."""
    if body.decision == DecisionStatus.PENDING:
        raise HTTPException(status_code=400, detail="decision cannot be PENDING")
    match = ctx.store.get_match(match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="match not found")
    _require_client_access(ctx, match.client_id)

    before = {"status": match.status.value, "client_id": match.client_id}
    _apply_match_correction(ctx, match, body)
    match.status = body.decision
    match.decided_by = ctx.actor.actor_id
    match.decided_at = date.today()
    match.reason = body.reason
    ctx.store.save_matches([match])
    ctx.store.append(
        AuditEntry.now(
            entity_kind="match",
            entity_id=match_id,
            action=f"decision:{body.decision.value.lower()}",
            author=ctx.actor.actor_id,
            reason=body.reason,
            before=before,
            after={"status": match.status.value, "client_id": match.client_id},
        )
    )
    return serialize_match(match)


@router.get("/contracts")
def list_contracts(
    client_id: str | None = Query(default=None),
    ctx: ApiContext = Depends(get_context),
) -> list[dict[str, Any]]:
    """List contracts visible to the actor (EF-CTR-02, EF-TDB-06)."""
    if client_id is not None:
        _require_client_access(ctx, client_id)
    clients = ctx.store.list_clients()
    contracts = ctx.store.list_contracts(client_id=client_id)
    visible = filter_by_clients(contracts, ctx.actor, clients)
    return [redact_contract_for_actor(c, ctx.actor) for c in visible]


@router.get("/contracts/{contract_id}")
def get_contract(
    contract_id: str,
    version: int | None = Query(default=None),
    ctx: ApiContext = Depends(get_context),
) -> dict[str, Any]:
    """Fetch a contract with extracted fields and source spans (EF-CTR-02)."""
    contract = ctx.store.get_contract(contract_id, version=version)
    if contract is None:
        raise HTTPException(status_code=404, detail="contract not found")
    _require_client_access(ctx, contract.client_id)
    return redact_contract_for_actor(contract, ctx.actor)


@router.put("/contracts/{contract_id}/fields")
def update_contract_fields(
    contract_id: str,
    body: ContractFieldsUpdateRequest,
    version: int | None = Query(default=None),
    ctx: ApiContext = Depends(get_context),
) -> dict[str, Any]:
    """Correct extracted Annex B fields on a contract (EF-CTR-02, EF-VAL-02)."""
    if ctx.actor.is_account_manager:
        raise HTTPException(status_code=403, detail="account managers cannot edit contract clauses")
    contract = ctx.store.get_contract(contract_id, version=version)
    if contract is None:
        raise HTTPException(status_code=404, detail="contract not found")

    before = serialize_contract_snapshot(contract)
    try:
        apply_field_updates(contract.fields, body.fields)
    except (ValueError, ArithmeticError) as exc:
        raise HTTPException(status_code=422, detail=f"invalid field value: {exc}") from exc

    ctx.store.save_contract(contract)
    ctx.store.append(
        AuditEntry.now(
            entity_kind="contract",
            entity_id=contract_id,
            action="update_fields",
            author=ctx.actor.actor_id,
            reason=body.reason,
            before=before,
            after=serialize_contract_snapshot(contract),
        )
    )
    return redact_contract_for_actor(contract, ctx.actor)


@router.post("/contracts/{contract_id}/validate")
def validate_contract(
    contract_id: str,
    body: ContractValidateRequest,
    version: int | None = Query(default=None),
    ctx: ApiContext = Depends(get_context),
) -> dict[str, Any]:
    """Validate a contract so it enters margin calculations (EF-CTR-03, EF-VAL-02)."""
    if ctx.actor.is_account_manager:
        raise HTTPException(status_code=403, detail="only controller or leadership may validate contracts")
    contract = ctx.store.get_contract(contract_id, version=version)
    if contract is None:
        raise HTTPException(status_code=404, detail="contract not found")

    before = serialize_contract_snapshot(contract)
    if body.corrections:
        try:
            apply_field_updates(contract.fields, body.corrections)
        except (ValueError, ArithmeticError) as exc:
            raise HTTPException(status_code=422, detail=f"invalid correction: {exc}") from exc

    contract.status = ContractStatus.VALIDATED
    contract.validated_by = ctx.actor.actor_id
    contract.validated_at = date.today()
    contract.validation_reason = body.reason
    ctx.store.save_contract(contract)
    ctx.store.append(
        AuditEntry.now(
            entity_kind="contract",
            entity_id=contract_id,
            action="validate",
            author=ctx.actor.actor_id,
            reason=body.reason,
            before=before,
            after=serialize_contract_snapshot(contract),
        )
    )
    return redact_contract_for_actor(contract, ctx.actor)


@router.get("/classifications")
def list_classifications(
    status: str | None = Query(default=None),
    client_id: str | None = Query(default=None),
    month: str | None = Query(default=None),
    ctx: ApiContext = Depends(get_context),
) -> list[dict[str, Any]]:
    """List classifications (e.g. ``?status=pending``) under RLS (EF-CLS-03)."""
    if client_id is not None:
        _require_client_access(ctx, client_id)
    parsed_month: Month | None = None
    if month is not None:
        try:
            parsed_month = Month.parse(month)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    normalized_status = status.upper() if status else None
    rows = ctx.store.list_classifications(
        status=normalized_status,
        client_id=client_id,
        month=parsed_month,
    )
    clients = ctx.store.list_clients()
    visible = filter_by_clients(rows, ctx.actor, clients)
    iv_map = {iv.intervention_id: iv for iv in ctx.store.list_interventions(month=parsed_month)}
    return [serialize_classification(c, iv_map.get(c.intervention_id)) for c in visible]


def _remember_category_decision(
    ctx: ApiContext,
    cls: Classification,
    reason: str,
) -> None:
    """Persist category decision memory when an intervention category is known (EF-CLS-04)."""
    interventions = ctx.store.list_interventions(client_id=cls.client_id)
    iv = next((i for i in interventions if i.intervention_id == cls.intervention_id), None)
    # A classification carries the contract version only: pick the lowest
    # contract id at that version so the choice is deterministic.
    candidates = sorted(
        (c for c in ctx.store.list_contracts(client_id=cls.client_id) if c.version == cls.contract_version),
        key=lambda c: c.contract_id,
    )
    contract = candidates[0] if candidates else None
    if iv and contract and cls.status in (DecisionStatus.APPROVED, DecisionStatus.CORRECTED):
        ctx.store.save_category_decision(
            CategoryDecision(
                contract_id=contract.contract_id,
                contract_version=cls.contract_version,
                category=iv.category,
                work_class=cls.work_class,
                decided_by=ctx.actor.actor_id,
                decided_at=date.today(),
                reason=reason,
            )
        )


@router.post("/classifications/{intervention_id}/decision")
def decide_classification(
    intervention_id: str,
    body: DecisionRequest,
    ctx: ApiContext = Depends(get_context),
) -> dict[str, Any]:
    """Validate, correct or discard a classification (EF-CLS-03, EF-VAL-02)."""
    if body.decision == DecisionStatus.PENDING:
        raise HTTPException(status_code=400, detail="decision cannot be PENDING")
    cls = _find_classification(ctx, intervention_id)
    if cls is None:
        raise HTTPException(status_code=404, detail="classification not found")
    _require_client_access(ctx, cls.client_id)

    before = {"status": cls.status.value, "work_class": cls.work_class.value}
    _apply_work_class_correction(cls, body)

    cls.status = body.decision
    cls.decided_by = ctx.actor.actor_id
    cls.decided_at = date.today()
    cls.decision_reason = body.reason
    ctx.store.save_classification(cls)
    _remember_category_decision(ctx, cls, body.reason)
    ctx.store.append(
        AuditEntry.now(
            entity_kind="classification",
            entity_id=intervention_id,
            action=f"decision:{body.decision.value.lower()}",
            author=ctx.actor.actor_id,
            reason=body.reason,
            before=before,
            after={"status": cls.status.value, "work_class": cls.work_class.value},
        )
    )
    iv_map = {iv.intervention_id: iv for iv in ctx.store.list_interventions(client_id=cls.client_id)}
    return serialize_classification(cls, iv_map.get(intervention_id))
