"""Row-level filtering and non-disclosure rules (spec 6, EF-TDB-06, ENF-CONF-03..04).

Rules enforced by this module:

1. **Client isolation (EF-TDB-06):** an ``ACCOUNT_MANAGER`` sees **only** the
   clients where they are the account manager. Direction, controller and
   administrator see every client.
2. **Hourly cost non-disclosure (ENF-CONF-03):** hourly costs are never
   disclosed to an account manager; only the controller and leadership may
   read them. The value is replaced by a redaction marker.
3. **AWS discount non-disclosure (ENF-CONF-04):** the wholesale discounts AWS
   grants the MSP, and the internal labour cost spread, stay out of account
   manager responses.

Pure functions: standard library only, deterministic, unit-testable.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from ..domain import Client, Contract, Rate
from .auth import Actor
from .serializers import serialize_contract

REDACTED_RATE = "[CONFIDENTIAL]"

CONFIDENTIAL_KEYS = ("hourly_cost", "labour_cost", "internal_discount", "aws_discount")


def visible_client_ids(actor: Actor, clients: Sequence[Client]) -> set[str]:
    """Return the set of client ids the actor is allowed to read."""
    if actor.sees_all_clients:
        return {c.client_id for c in clients}
    return {c.client_id for c in clients if c.account_manager_id == actor.actor_id}


def can_access_client(actor: Actor, client_id: str, clients: Sequence[Client]) -> bool:
    """True if ``actor`` may access rows belonging to ``client_id``."""
    return client_id in visible_client_ids(actor, clients)


def _client_id_of(item: Any, client_id_attr: str) -> str | None:
    if isinstance(item, dict):
        return item.get(client_id_attr)
    return getattr(item, client_id_attr, None)


def filter_by_clients(
    items: Iterable[Any],
    actor: Actor,
    clients: Sequence[Client],
    client_id_attr: str = "client_id",
) -> list[Any]:
    """Keep the rows of the clients the actor may read (EF-TDB-06).

    A row with no client id is a shared reference (for instance a tooling rule
    spread over every client): it stays visible, since it names no other client.
    """
    allowed = visible_client_ids(actor, clients)
    kept: list[Any] = []
    for item in items:
        owner = _client_id_of(item, client_id_attr)
        if owner is None or owner in allowed:
            kept.append(item)
    return kept


def redact_rates_for_actor(rates: Sequence[Rate], actor: Actor) -> list[dict[str, Any]]:
    """ENF-CONF-03: hourly costs are kept away from account managers."""
    rows: list[dict[str, Any]] = []
    for entry in rates:
        rows.append(
            {
                "level": entry.level.value,
                "effective_from": str(entry.effective_from),
                "currency": entry.currency,
                "hourly_cost": str(entry.hourly_cost) if actor.sees_hourly_costs else REDACTED_RATE,
            }
        )
    return rows


def redact_contract_for_actor(contract: Contract, actor: Actor) -> dict[str, Any]:
    """Serialize a contract; labour-cost figures follow ENF-CONF-03."""
    return redact_row(serialize_contract(contract), actor)


def redact_row(row: dict[str, Any], actor: Actor) -> dict[str, Any]:
    """Hide confidential cost and AWS discount keys from non-management roles."""
    if actor.sees_hourly_costs:
        return dict(row)
    copied = dict(row)
    for key in CONFIDENTIAL_KEYS:
        if key in copied:
            copied[key] = REDACTED_RATE
    return copied


def row_filter(actor: Actor, clients: Sequence[Client], client_id: str | None) -> bool:
    """Predicate answering whether ``actor`` may query rows of ``client_id``."""
    if actor.sees_all_clients:
        return True
    if client_id is None:
        return False
    return client_id in visible_client_ids(actor, clients)
