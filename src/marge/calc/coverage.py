"""Data coverage calculation (spec 12.4, EF-ADM-02).

Coverage is the ratio of hours attached to a client and a contract divided by
all recorded hours in the month.

Domain layer: standard library only.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from ..domain import UNASSIGNED_CLIENT_ID, Coverage, Intervention, hours


def compute_coverage(interventions: Sequence[Intervention]) -> Coverage:
    """Compute overall coverage across a set of interventions."""
    total = sum((i.hours_spent for i in interventions), Decimal("0"))
    attributed = sum(
        (i.hours_spent for i in interventions if i.client_id and i.client_id != UNASSIGNED_CLIENT_ID),
        Decimal("0"),
    )
    return Coverage(total_hours=hours(total), attributed_hours=hours(attributed))
