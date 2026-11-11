"""The three MCP tools of spec 14.3.

Every figure comes from the store (computed by ``marge.calc``), never from the
agent. Each tool validates its arguments and passes the guards first.
"""

from __future__ import annotations

from datetime import date

from ..domain import Month, UnbilledState
from .guards import (
    assert_can_see_costs,
    assert_client_visible,
    assert_single_open_dossier,
    draft_marker,
)
from .server import Tool

CLIENT_ARG = {
    "type": "object",
    "properties": {
        "client_id": {"type": "string", "description": "Common client identifier, e.g. c-007"},
    },
    "required": ["client_id"],
}

MONTH_ARG = {
    "type": "object",
    "properties": {
        "client_id": {"type": "string"},
        "month": {"type": "string", "description": "YYYY-MM"},
    },
    "required": ["client_id", "month"],
}


def _month(raw: str) -> Month:
    try:
        return Month.parse(raw)
    except ValueError as exc:
        raise ValueError(f"invalid month {raw!r}: expected YYYY-MM") from exc


def _client_or_raise(ctx, client_id: str):
    client = ctx.store.get_client(client_id)
    if client is None:
        raise LookupError(f"unknown client {client_id}")
    return client


def _dossier(ctx, client_id: str, month: Month) -> str:
    """The quantified file attached to a renegotiation task."""
    margins = ctx.store.list_margin_months(client_id=client_id, month=month)
    hours = [h for h in ctx.store.list_hours_summaries(client_id) if h.month == month]
    lines = ctx.store.margin_lines(client_id, month)
    margin = margins[0] if margins else None
    unbilled = hours[0] if hours else None
    parts = [f"Client {client_id} — {month}"]
    if margin is not None:
        parts.append(
            f"revenue {margin.revenue.total}, costs {margin.costs.total}, "
            f"margin {margin.margin} ({margin.margin_rate})"
        )
    if unbilled is not None:
        parts.append(f"unbilled {unbilled.unbilled_hours} h = {unbilled.unbilled_value}")
    parts.append(f"{len(lines)} source line(s) attached")
    return "\n".join(parts)


def create_renegotiation_task(ctx, client_id: str, reason: str = "") -> dict:
    """Create a renegotiation task in the ticket tool, with the quantified file."""
    assert_client_visible(ctx, client_id)
    _client_or_raise(ctx, client_id)
    assert_single_open_dossier(ctx, client_id)
    month = ctx.extra.get("month") or Month.of(date.today())
    dossier = _dossier(ctx, client_id, month)
    if reason:
        dossier = f"{dossier}\nreason: {reason}"
    itsm = getattr(ctx, "itsm", None)
    task_id = itsm.create_renegotiation_task(client_id, ctx.actor_id, dossier) if itsm else ""
    return {
        "client_id": client_id,
        "task_id": task_id,
        "month": str(month),
        "dossier": dossier,
        "created_by": ctx.actor_id,
    }


def draft_extra_billing_proposal(ctx, client_id: str, month: str) -> dict:
    """Prepare a DRAFT extra-billing proposal from the validated hours."""
    assert_client_visible(ctx, client_id)
    _client_or_raise(ctx, client_id)
    target = _month(month)
    summaries = [h for h in ctx.store.list_hours_summaries(client_id) if h.month == target]
    if not summaries:
        raise LookupError(f"no hours summary for {client_id} in {target}")
    summary = summaries[0]
    proposal = {
        "client_id": client_id,
        "month": str(target),
        "hours": str(summary.out_of_scope_validated_hours),
        "hour_rate": str(summary.contract_hour_rate),
        "amount": str(summary.unbilled_value),
        "state": UnbilledState.DETECTED.value,
    }
    itsm = getattr(ctx, "itsm", None)
    if itsm is not None:
        proposal["draft_id"] = itsm.store_billing_draft(client_id, str(proposal))
    return draft_marker(proposal)


def get_margin_breakdown(ctx, client_id: str, month: str) -> dict:
    """Read-only breakdown of a margin, down to its source lines."""
    assert_client_visible(ctx, client_id)
    _client_or_raise(ctx, client_id)
    target = _month(month)
    margins = ctx.store.list_margin_months(client_id=client_id, month=target)
    if not margins:
        raise LookupError(f"no margin for {client_id} in {target}")
    margin = margins[0]
    payload = {
        "client_id": client_id,
        "month": str(target),
        "revenue": str(margin.revenue.total),
        "costs": str(margin.costs.total),
        "margin": str(margin.margin),
        "margin_rate": str(margin.margin_rate),
        "state": margin.state.value,
        "coverage": str(margin.coverage.percent),
        "dashboard": f"/dashboards/client/{client_id}?month={target}",
        "lines": [
            {"post": line.post, "label": line.label, "amount": str(line.amount)}
            for line in ctx.store.margin_lines(client_id, target)
        ],
    }
    if ctx.role.value in {"CONTROLLER", "EXECUTIVE", "ADMINISTRATOR"}:
        assert_can_see_costs(ctx)
        payload["costs_breakdown"] = {
            "labour": str(margin.costs.labour),
            "tooling": str(margin.costs.tooling),
            "msp_aws": str(margin.costs.msp_aws),
            "penalties": str(margin.costs.penalties),
        }
    else:
        payload["costs_breakdown"] = "restricted"
    return payload


def _renegotiation(ctx, args: dict) -> dict:
    return create_renegotiation_task(ctx, args["client_id"], args.get("reason", ""))


def _proposal(ctx, args: dict) -> dict:
    return draft_extra_billing_proposal(ctx, args["client_id"], args["month"])


def _breakdown(ctx, args: dict) -> dict:
    return get_margin_breakdown(ctx, args["client_id"], args["month"])


TOOLS = (
    Tool(
        name="create_renegotiation_task",
        description=(
            "Create a renegotiation task for the account manager in the ticket tool, "
            "with the quantified client file attached. One open dossier per client."
        ),
        input_schema={
            **CLIENT_ARG,
            "properties": {**CLIENT_ARG["properties"], "reason": {"type": "string"}},
        },
        handler=_renegotiation,
    ),
    Tool(
        name="draft_extra_billing_proposal",
        description=(
            "Prepare a DRAFT extra-billing proposal from the validated out-of-scope "
            "hours. Nothing is sent to the client."
        ),
        input_schema=MONTH_ARG,
        handler=_proposal,
    ),
    Tool(
        name="get_margin_breakdown",
        description="Read-only margin breakdown down to its source lines, per caller rights.",
        input_schema=MONTH_ARG,
        handler=_breakdown,
    ),
)
