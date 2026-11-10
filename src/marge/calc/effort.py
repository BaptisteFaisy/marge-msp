"""Effort slices by category and level (spec 12.3, EF-CAL-05).

Domain layer: standard library only.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from ..domain import EffortSlice, Settings, WorkClass, WorkLevel, hours, money
from .inputs import MarginInputs
from .rates import rate_in_force


def compute_effort_slices(inputs: MarginInputs, settings: Settings) -> list[EffortSlice]:  # noqa: ARG001
    """Breakdown of labour by (category, level) for Quick table 2.

    ``settings`` is part of the common signature of every calculation entry
    point (docs/CONTRACT.md) even when a given computation does not need it.
    """
    class_map = {c.intervention_id: c for c in inputs.classifications}

    buckets: dict[tuple[str, WorkLevel, WorkClass], list[Decimal]] = defaultdict(list)

    for iv in inputs.interventions:
        cls = class_map.get(iv.intervention_id)
        wclass = cls.work_class if cls else WorkClass.INCLUDED
        buckets[(iv.category, iv.level, wclass)].append(iv.hours_spent)

    slices: list[EffortSlice] = []
    for (cat, lvl, wclass), duration_list in sorted(buckets.items()):
        total_h = sum(duration_list, Decimal("0"))
        rate = rate_in_force(inputs.rates, lvl, inputs.month)
        hourly = rate.hourly_cost if rate else Decimal("0")
        labour = money(total_h * hourly)
        slices.append(
            EffortSlice(
                client_id=inputs.client.client_id,
                month=inputs.month,
                category=cat,
                level=lvl,
                hours_spent=hours(total_h),
                labour_cost=labour,
                ticket_count=len(duration_list),
                work_class=wclass,
            )
        )
    return slices
