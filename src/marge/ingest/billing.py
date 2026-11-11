"""AWS billing export loading (EF-SRC-02, spec 12.1).

The billing export is in USD, the contracts in EUR: the conversion happens
here, once, with the rate of the month. ``marge.calc`` only ever sees one
currency (see docs/DATA-FORMATS.md).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from decimal import Decimal, InvalidOperation

from ..domain import AwsCost, AwsCostKind, Month, SourceKind
from ..match import MappingResolver


def parse_fx(rows: Iterable[dict[str, str]]) -> dict[tuple[Month, str, str], Decimal]:
    """``(month, from, to) -> rate`` from ``fx.csv``."""
    rates: dict[tuple[Month, str, str], Decimal] = {}
    for row in rows:
        month = Month.parse(row["month"])
        rates[(month, row["from"].upper(), row["to"].upper())] = Decimal(str(row["rate"]))
    return rates


def convert(amount: Decimal, month: Month, source_currency: str, target: str, rates: dict) -> Decimal:
    """Convert an amount to the reporting currency, 1:1 when already there."""
    src, dst = (source_currency or target).upper(), target.upper()
    if src == dst:
        return amount
    rate = rates.get((month, src, dst))
    if rate is None:
        # A missing rate must never invent a value: the caller flags the row.
        raise KeyError(f"no FX rate {src}->{dst} for {month}")
    return amount * rate


def _decimal(raw: str | None) -> Decimal:
    try:
        return Decimal((raw or "0").replace(",", ".").strip())
    except InvalidOperation:
        return Decimal("0")


def to_aws_cost(
    row: dict[str, str],
    resolver: MappingResolver,
    rates: dict,
    reporting_currency: str = "EUR",
) -> AwsCost:
    """Build one ``AwsCost`` in the reporting currency."""
    month = Month.parse(row["month"])
    currency = (row.get("currency") or reporting_currency).upper()
    cost = convert(_decimal(row.get("cost")), month, currency, reporting_currency, rates)
    rebilled = convert(_decimal(row.get("rebilled_amount")), month, currency, reporting_currency, rates)
    kind = AwsCostKind((row.get("kind") or "CLIENT_ACCOUNT").strip().upper())
    client_ref = (row.get("client_ref") or "").strip()
    client_id = resolver.resolve(SourceKind.BILLING, client_ref) if client_ref else None
    return AwsCost(
        aws_account_id=row["aws_account_id"].strip(),
        month=month,
        cost=cost,
        kind=kind,
        client_id=client_id,
        rebilled_amount=rebilled,
        currency=reporting_currency,
    )


def load_aws_costs(
    rows: Iterable[dict[str, str]],
    resolver: MappingResolver,
    rates: dict,
    reporting_currency: str = "EUR",
) -> Iterator[AwsCost]:
    """Turn billing rows into ``AwsCost`` in the reporting currency."""
    for row in rows:
        yield to_aws_cost(row, resolver, rates, reporting_currency)
