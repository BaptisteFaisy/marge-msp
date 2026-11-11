"""Margin calculation package (spec 12).

The whole package is pure: standard library only, no I/O, deterministic.
Every figure displayed anywhere in Marge comes from here.
"""

from __future__ import annotations

from .allocation import allocate_tooling
from .coverage import compute_coverage
from .effort import compute_effort_slices
from .hours import compute_hours_summary
from .inputs import AllocationContext, MarginInputs
from .margin import compute_margin_month
from .rates import rate_in_force
from .renewal import build_renewal_watch, six_month_margin_rate, trend_of
from .trace import margin_lines
from .versioning import CalcVersion, MarginDiff, VersionHistory, diff_versions, summarise_diff

__all__ = [
    "AllocationContext",
    "CalcVersion",
    "MarginDiff",
    "MarginInputs",
    "VersionHistory",
    "allocate_tooling",
    "build_renewal_watch",
    "compute_coverage",
    "compute_effort_slices",
    "compute_hours_summary",
    "compute_margin_month",
    "diff_versions",
    "margin_lines",
    "rate_in_force",
    "six_month_margin_rate",
    "summarise_diff",
    "trend_of",
]
