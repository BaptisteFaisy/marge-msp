"""Renewal watch (EF-CTR-05, EF-TDB-04).

Domain layer: standard library only.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from ..domain import Contract, ContractStatus, MarginMonth, Month, RenewalWatch, days_between, ratio


def trend_of(margins: Sequence[MarginMonth]) -> str:
    """Compare the last two months: ``UP``, ``DOWN`` or ``FLAT``."""
    ordered = sorted(margins, key=lambda m: m.month)
    if len(ordered) < 2:
        return "FLAT"
    delta = ordered[-1].margin_rate - ordered[-2].margin_rate
    if delta > Decimal("0.005"):
        return "UP"
    if delta < Decimal("-0.005"):
        return "DOWN"
    return "FLAT"


def six_month_margin_rate(margins: Sequence[MarginMonth]) -> Decimal:
    revenue = sum((m.revenue.total for m in margins), Decimal("0"))
    cost = sum((m.costs.total for m in margins), Decimal("0"))
    return ratio(revenue - cost, revenue)


def build_renewal_watch(
    contracts: Sequence[Contract],
    margins: Sequence[MarginMonth],
    today: date,
    horizon_days: int = 90,
) -> list[RenewalWatch]:
    """Contracts renewing within ``horizon_days``, with margin and trend."""
    watch: list[RenewalWatch] = []
    for contract in contracts:
        if contract.status != ContractStatus.VALIDATED or contract.fields.end_date is None:
            continue
        days = days_between(today, contract.fields.end_date)
        if days > horizon_days:
            continue
        own = [m for m in margins if m.client_id == contract.client_id]
        watch.append(
            RenewalWatch(
                client_id=contract.client_id,
                contract_id=contract.contract_id,
                contract_version=contract.version,
                end_date=contract.fields.end_date,
                days_to_renewal=days,
                monthly_subscription=contract.fields.monthly_subscription,
                margin_rate_six_months=six_month_margin_rate(own),
                trend=trend_of(own),
            )
        )
    return sorted(watch, key=lambda w: w.days_to_renewal)


def months_covered(margins: Sequence[MarginMonth], end: Month, count: int = 6) -> list[Month]:
    """The ``count`` months ending at ``end`` that have a computed margin."""
    window = [end.add_months(-i) for i in range(count)]
    present = {m.month for m in margins}
    return [m for m in reversed(window) if m in present]
