"""Deterministic client identity matcher (offline stand-in for ``marge.match``).

EF-REF-01: the tool proposes a correspondence between the sources and the
common client id, with a confidence, and a human validates it. CI has no
credentials and no model, so the harness runs this rule-based matcher instead.

It only ever sees what a connector sees — the source kind, the source id and
the name the source uses — never the common id it is supposed to find. That is
what makes the R2 measure meaningful rather than tautological.

Ambiguity is reported, not hidden: when two clients score the same, the
confidence is halved and the proposal stays PENDING, so it never joins the
validated set the calculation relies on.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from ..domain import ClientMatch, DecisionStatus, SourceKind
from .fields import normalise_text

THRESHOLD = Decimal("0.80")
"""Below this confidence a proposal is not auto-suggested (settings default)."""

NOISE = frozenset(
    {
        "sas",
        "sarl",
        "sa",
        "sci",
        "eurl",
        "sasu",
        "ancien",
        "code",
        "client",
        "prod",
        "production",
        "groupe",
        "the",
    }
)


def _tokens(text: str) -> set[str]:
    """Significant words of a name, plurals and legal forms removed."""
    words = {
        word.strip(".,;:()«»\"'") for word in normalise_text(text).replace("-", " ").split() if len(word) >= 3
    }
    return {word for word in words if word not in NOISE}


def similarity(left: set[str], right: set[str]) -> Decimal:
    """Share of the longest name found in the other one (0 to 1)."""
    if not left or not right:
        return Decimal("0")
    shared = len(left & right)
    if shared == 0:
        return Decimal("0")
    return (Decimal(shared) / Decimal(max(len(left), len(right)))).quantize(Decimal("0.0001"))


def _candidates(variant: str, clients: Sequence[tuple[str, str]]) -> list[tuple[Decimal, str]]:
    """Score every client against one alias name, best first."""
    tokens = _tokens(variant)
    scored = [(similarity(tokens, _tokens(name)), client_id) for client_id, name in clients]
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return scored


def best_candidate(variant: str, clients: Sequence[tuple[str, str]]) -> tuple[Decimal, str]:
    """Best client for one alias, with a confidence halved on a tie."""
    scored = _candidates(variant, clients)
    if not scored or scored[0][0] == 0:
        return Decimal("0"), ""
    score, client_id = scored[0]
    if len(scored) > 1 and scored[1][0] == score:
        return (score / 2).quantize(Decimal("0.0001")), client_id
    return score, client_id


def propose_matches(
    aliases: Sequence[dict],
    clients: Sequence[tuple[str, str]],
    threshold: Decimal = THRESHOLD,
) -> list[ClientMatch]:
    """Propose one match per alias; only confident ones are auto-validated.

    ``aliases`` carries ``source``, ``source_id`` and ``name_variant`` — and
    deliberately **not** the client id, which is the answer being searched.
    """
    matches: list[ClientMatch] = []
    for index, alias in enumerate(aliases, start=1):
        confidence, client_id = best_candidate(alias["name_variant"], clients)
        approved = client_id != "" and confidence >= threshold
        matches.append(
            ClientMatch(
                match_id=f"m-{index:03d}",
                client_id=client_id or "UNRESOLVED",
                source=SourceKind(alias["source"]),
                source_id=str(alias["source_id"]),
                confidence=confidence,
                status=DecisionStatus.APPROVED if approved else DecisionStatus.PENDING,
                decided_by="controller-01" if approved else None,
                reason="name similarity above threshold" if approved else "to be reviewed",
            )
        )
    return matches
