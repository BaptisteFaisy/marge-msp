"""The guards around the agent's actions (spec 14.3).

Three rules, each one a test:

* one open renegotiation dossier per client;
* the extra-billing proposal is a DRAFT — nothing is ever sent to the client;
* the margin breakdown is read only, and an account manager never sees the
  hourly costs (ENF-CONF-03).
"""

from __future__ import annotations

from ..domain import ActorRole

COST_VISIBLE_ROLES = (ActorRole.CONTROLLER, ActorRole.EXECUTIVE, ActorRole.ADMINISTRATOR)


class GuardViolation(PermissionError):
    """Raised when an action would break one of the guards."""


def assert_single_open_dossier(ctx, client_id: str) -> None:
    """Refuse a second open renegotiation dossier for the same client."""
    itsm = getattr(ctx, "itsm", None)
    if itsm is None:
        return
    if itsm.open_task_exists(client_id, "renegotiation"):
        raise GuardViolation(
            f"a renegotiation dossier is already open for {client_id}: close it before creating a new one"
        )


def assert_can_see_costs(ctx) -> None:
    """Only the controller, the direction and the administrator see rates."""
    if ctx.role not in COST_VISIBLE_ROLES:
        raise GuardViolation("hourly costs are restricted to the controller and the direction")


def assert_client_visible(ctx, client_id: str) -> None:
    """An account manager only reaches their own clients (EF-TDB-06)."""
    if ctx.role != ActorRole.ACCOUNT_MANAGER:
        return
    client = ctx.store.get_client(client_id)
    if client is None:
        raise LookupError(f"unknown client {client_id}")
    if client.account_manager_id != ctx.actor_id:
        raise GuardViolation(f"{ctx.actor_id} is not the account manager of {client_id}")


def draft_marker(proposal: dict) -> dict:
    """Stamp a proposal so no caller can mistake it for a sent document."""
    proposal["status"] = "DRAFT"
    proposal["sent"] = False
    proposal["note"] = "Draft only: nothing was sent to the client."
    return proposal
