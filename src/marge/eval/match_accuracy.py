"""Client identity matching accuracy (spec 13.3, R2).

Two numbers matter, and the measure reports both: more than 80 % of the
*proposed* matches must be right, and **100 %** of the matches a human
validated must be right (EF-REF-01: a human validates, so an approved match is
the one the calculation will use).
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from ..domain import ClientMatch, DecisionStatus
from .score import Score, score_of

TARGET = Decimal("0.80")
VALIDATED_TARGET = Decimal("0.99")

ACCEPTED = (DecisionStatus.APPROVED, DecisionStatus.CORRECTED)


def _pairs(matches: Sequence[ClientMatch]) -> set[tuple[str, str]]:
    return {(match.client_id, match.source_id) for match in matches}


def match_accuracy(matches: Sequence[ClientMatch], truth: Sequence[tuple[str, str]]) -> Score:
    """How many proposed matches are right, and whether validation is clean."""
    expected = {(client_id, source_id) for client_id, source_id in truth}
    proposed = list(matches)
    correct = sum(1 for match in proposed if (match.client_id, match.source_id) in expected)
    validated = [match for match in proposed if match.status in ACCEPTED]
    validated_correct = sum(1 for match in validated if (match.client_id, match.source_id) in expected)
    validated_ratio = Decimal(validated_correct) / Decimal(len(validated)) if validated else Decimal("0")
    detail = [
        f"{len(proposed)} proposed match(es) for {len(expected)} expected pair(s)",
        f"validated: {validated_correct}/{len(validated)} = {validated_ratio * 100:.2f}% (must be 100%)",
    ]
    for match in proposed:
        if (match.client_id, match.source_id) not in expected:
            detail.append(
                f"wrong proposal: {match.source_id} -> {match.client_id} (confidence {match.confidence})"
            )
    unresolved = sorted(expected - _pairs(validated))
    if unresolved:
        detail.append(f"not validated: {len(unresolved)} pair(s)")
    forced = bool(validated) and validated_ratio <= VALIDATED_TARGET
    if not validated:
        detail.append("no validated match: R2 cannot be met")
        forced = True
    return score_of(correct, len(proposed), TARGET, detail, forced_failure=forced)
