"""Effective-dated rate lookup (spec 12.2, 12.4, EF-REF-02).

Domain layer: standard library only.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..domain import Month, Rate, WorkLevel, effective_value


def rate_in_force(rates: Sequence[Rate], level: WorkLevel, month: Month) -> Rate | None:
    """Find the loaded hourly cost in force for ``level`` during ``month``."""
    level_rates = [r for r in rates if r.level == level]
    at = month.last_day()
    return effective_value(level_rates, at)
