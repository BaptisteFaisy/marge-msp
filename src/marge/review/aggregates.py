"""Aggregates behind the monthly review (spec 8.4, 14.4, EF-REV-01).

Every figure here comes from the store, i.e. from ``marge.calc``. The review
text only formats them: it never computes anything (ENF-IA-01), which is what
makes R14 (review figures == dashboard figures) checkable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ..calc import build_renewal_watch, trend_of
from ..domain import MarginMonth, Month, RenewalWatch, Settings, ratio
from ..store.base import Store


@dataclass(frozen=True, slots=True)
class ClientFigure:
    """One client line of the review."""

    client_id: str
    name: str
    margin: Decimal
    margin_rate: Decimal
    cause: str


@dataclass(frozen=True, slots=True)
class VariationFigure:
    """A month-over-month variation worth explaining."""

    client_id: str
    name: str
    delta_rate: Decimal
    explanation: str


@dataclass(slots=True)
class ReviewInputs:
    """Everything the Annex E template needs, already computed."""

    month: Month
    total_margin: Decimal
    total_margin_rate: Decimal
    previous_margin_rate: Decimal
    coverage_percent: Decimal
    threshold: Decimal
    clients_below_threshold: list[ClientFigure] = field(default_factory=list)
    variations: list[VariationFigure] = field(default_factory=list)
    unbilled_hours: Decimal = Decimal("0")
    unbilled_value: Decimal = Decimal("0")
    unbilled_clients: list[tuple[str, Decimal, Decimal]] = field(default_factory=list)
    renewals: list[RenewalWatch] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)

    @property
    def margin_variation_points(self) -> Decimal:
        return ((self.total_margin_rate - self.previous_margin_rate) * 100).quantize(Decimal("0.1"))

    @property
    def renewals_within_horizon(self) -> int:
        return len(self.renewals)


def _name_of(store: Store, client_id: str) -> str:
    client = store.get_client(client_id)
    return client.name if client else client_id


def _cause(margin: MarginMonth) -> str:
    if margin.costs.labour > margin.revenue.total:
        return f"labour {margin.costs.labour} above revenue {margin.revenue.total}"
    if margin.state.value == "INCOMPLETE":
        return margin.incomplete_reason or "no validated contract"
    biggest = max(
        (
            ("labour", margin.costs.labour),
            ("tooling", margin.costs.tooling),
            ("AWS", margin.costs.msp_aws),
            ("penalties", margin.costs.penalties),
        ),
        key=lambda pair: pair[1],
    )
    return f"largest cost item: {biggest[0]} {biggest[1]}"


def build_review_inputs(store: Store, month: Month, settings: Settings) -> ReviewInputs:
    """Compute every figure of the monthly review for one month."""
    rows = store.list_margin_months(month=month)
    previous = store.list_margin_months(month=month.previous())

    revenue = sum((r.revenue.total for r in rows), Decimal("0"))
    cost = sum((r.costs.total for r in rows), Decimal("0"))
    coverage = sum((r.coverage.percent for r in rows), Decimal("0")) / max(1, len(rows))

    below = [
        ClientFigure(
            client_id=row.client_id,
            name=_name_of(store, row.client_id),
            margin=row.margin,
            margin_rate=row.margin_rate,
            cause=_cause(row),
        )
        for row in rows
        if row.margin_rate < settings.margin_threshold
    ]
    below.sort(key=lambda figure: figure.margin_rate)

    variations = _variations(store, rows, previous)
    hours = [h for h in store.list_hours_summaries() if h.month == month]

    return ReviewInputs(
        month=month,
        total_margin=(revenue - cost).quantize(Decimal("0.01")),
        total_margin_rate=ratio(revenue - cost, revenue),
        previous_margin_rate=_previous_rate(previous),
        coverage_percent=coverage.quantize(Decimal("0.1")),
        threshold=settings.margin_threshold,
        clients_below_threshold=below,
        variations=variations,
        unbilled_hours=sum((h.unbilled_hours for h in hours), Decimal("0")),
        unbilled_value=sum((h.unbilled_value for h in hours), Decimal("0")),
        unbilled_clients=[
            (_name_of(store, h.client_id), h.unbilled_hours, h.unbilled_value)
            for h in sorted(hours, key=lambda h: h.unbilled_value, reverse=True)[:5]
            if h.unbilled_hours > 0
        ],
        renewals=build_renewal_watch(
            store.list_contracts(), rows, month.last_day(), settings.renewal_horizon_days
        ),
        decisions=_decisions(below, hours),
    )


def _previous_rate(previous: list[MarginMonth]) -> Decimal:
    revenue = sum((r.revenue.total for r in previous), Decimal("0"))
    cost = sum((r.costs.total for r in previous), Decimal("0"))
    return ratio(revenue - cost, revenue)


def _variations(store: Store, rows, previous) -> list[VariationFigure]:
    by_client = {row.client_id: row for row in previous}
    variations: list[VariationFigure] = []
    for row in rows:
        before = by_client.get(row.client_id)
        if before is None:
            continue
        delta = row.margin_rate - before.margin_rate
        if abs(delta) < Decimal("0.03"):
            continue
        direction = "rose" if delta > 0 else "baissée"
        variations.append(
            VariationFigure(
                client_id=row.client_id,
                name=_name_of(store, row.client_id),
                delta_rate=delta,
                explanation=(
                    f"la marge a {direction} de {(abs(delta) * 100).quantize(Decimal('0.1'))} point(s) "
                    f"({_cause(row)})"
                ),
            )
        )
    return sorted(variations, key=lambda v: abs(v.delta_rate), reverse=True)[:5]


def _decisions(below, hours) -> list[str]:
    """Three decision proposals, each one backed by a figure."""
    proposals: list[str] = []
    for figure in below[:2]:
        proposals.append(
            f"Renégocier {figure.name} : marge {figure.margin_rate} sous le seuil, {figure.cause}"
        )
    ranked = sorted(hours, key=lambda h: h.unbilled_value, reverse=True)
    if ranked and ranked[0].unbilled_value > 0:
        proposals.append(
            f"Facturer ou arrêter le hors périmètre de {ranked[0].client_id} : "
            f"{ranked[0].unbilled_hours} h = {ranked[0].unbilled_value}"
        )
    return proposals[:3]


def trend_label(rows: list[MarginMonth]) -> str:
    return trend_of(rows)
