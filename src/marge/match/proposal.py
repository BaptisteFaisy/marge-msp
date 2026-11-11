"""Proposing client matches (EF-REF-01, spec 13.3 target: > 80 % right).

A proposal is never authoritative: it is created in ``DecisionStatus.PENDING``
and the controller validates it in the portal (ENF-IA-02).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal

from ..domain import ClientMatch, DecisionStatus, Settings
from .normalise import Alias, ClientName, confidence_for, normalise_name


def _best_client(alias: Alias, clients: Sequence[ClientName]) -> tuple[str, Decimal]:
    best_id, best_conf = "", Decimal("0")
    for client in clients:
        conf = confidence_for(alias.name_variant, client.name)
        if conf > best_conf:
            best_id, best_conf = client.client_id, conf
    return best_id, best_conf


def _name_of(client_id: str, clients: Sequence[ClientName]) -> str:
    return next((c.name for c in clients if c.client_id == client_id), "")


def propose_matches(
    aliases: Sequence[Alias],
    clients: Sequence[ClientName],
    settings: Settings | None = None,
) -> list[ClientMatch]:
    """Propose one match per (source, source id), with a confidence level."""
    cfg = settings or Settings()
    proposals: list[ClientMatch] = []
    for alias in aliases:
        best_id, best_conf = _best_client(alias, clients)
        if not best_id or best_conf < cfg.match_confidence_threshold / 2:
            continue
        proposals.append(
            ClientMatch(
                match_id=f"m-{alias.source.value}-{alias.source_id}".lower(),
                client_id=best_id,
                source=alias.source,
                source_id=alias.source_id,
                confidence=best_conf,
                status=DecisionStatus.PENDING,
                reason=f"proposed from {alias.name_variant!r} -> {_name_of(best_id, clients)!r}",
            )
        )
    return proposals


def duplicate_ids(proposals: Sequence[ClientMatch]) -> dict[str, list[str]]:
    """Source ids proposed for more than one client (a red flag for the human)."""
    seen: dict[str, list[str]] = defaultdict(list)
    for proposal in proposals:
        seen[f"{proposal.source.value}:{proposal.source_id}"].append(proposal.client_id)
    return {key: ids for key, ids in seen.items() if len(set(ids)) > 1}


def normalised_variants(aliases: Sequence[Alias]) -> dict[str, set[str]]:
    """Debug helper: every normalised form seen for a client."""
    grouped: dict[str, set[str]] = defaultdict(set)
    for alias in aliases:
        grouped[alias.client_id].add(normalise_name(alias.name_variant))
    return dict(grouped)
