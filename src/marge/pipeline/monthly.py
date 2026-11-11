"""The monthly review run (spec 8.4, 14.4).

The scheduled Quick flow writes the review from the dashboards. This module is
the deterministic fallback (EF-REV-03): it produces the same review from the
aggregates, so the figures are identical to the dashboards (R14).
"""

from __future__ import annotations

from collections.abc import Callable

from ..domain import Month, Settings
from ..store.base import Store
from .reports import MonthlyReport

Renderer = Callable[[object, Settings], str]
Aggregator = Callable[[Store, Month, Settings], object]


def _resolve(aggregator: Aggregator | None, renderer: Renderer | None) -> tuple[Aggregator, Renderer]:
    """Bind the review module lazily so the pipeline has no hard dependency."""
    build = aggregator
    render = renderer
    if build is None or render is None:
        from ..review import aggregates as review_aggregates
        from ..review import template as review_template

        build = build or review_aggregates.build_review_inputs
        render = render or review_template.render_review
    return (build, render)


def run_monthly(
    store: Store,
    settings: Settings,
    month: Month,
    recipients: tuple[str, ...] = (),
    aggregator: Aggregator | None = None,
    renderer: Renderer | None = None,
) -> MonthlyReport:
    """Build the monthly review text and return it with its metadata."""
    build, render = _resolve(aggregator, renderer)
    inputs = build(store, month, settings)
    text = render(inputs, settings)
    return MonthlyReport(
        month=month,
        review_text=text,
        recipients=recipients,
        stored_at=f"reviews/{month}/profitability-review.md",
        figures=_figures(inputs),
    )


def _figures(inputs: object) -> dict[str, str]:
    """Expose the headline figures so the caller can compare with the dashboards."""
    figures: dict[str, str] = {}
    for name in (
        "total_margin",
        "total_margin_rate",
        "coverage_percent",
        "unbilled_hours",
        "unbilled_value",
        "clients_below_threshold",
        "renewals_within_horizon",
    ):
        value = getattr(inputs, name, None)
        if value is not None:
            figures[name] = str(value)
    return figures
