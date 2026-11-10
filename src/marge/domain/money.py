"""Money and hours arithmetic.

Every amount in Marge is a :class:`Decimal`. The language model never computes
a number (ENF-IA-01): all arithmetic lives here and in ``marge.calc``.

Domain layer: standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal("0.01")
HOURS_PRECISION = Decimal("0.01")
RATE_PRECISION = Decimal("0.0001")
DEFAULT_CURRENCY = "EUR"


class CurrencyMismatch(ValueError):
    """Raised when two amounts with different currencies are combined."""


def dec(value: object) -> Decimal:
    """Coerce ``int``, ``float``, ``str`` or ``Decimal`` into a Decimal."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(str(value))


def money(value: object, currency: str = DEFAULT_CURRENCY) -> Decimal:  # noqa: ARG001
    """Round a value to cents using HALF_UP rounding.

    ``currency`` is accepted (and ignored) so callers can pass the currency of
    the source document: conversion happens in the connectors, never here.
    """
    return dec(value).quantize(CENTS, rounding=ROUND_HALF_UP)


def hours(value: object) -> Decimal:
    """Round a duration to hundredths of an hour."""
    return dec(value).quantize(HOURS_PRECISION, rounding=ROUND_HALF_UP)


def rate(value: object) -> Decimal:
    """Round an hourly rate to four decimals (kept for auditability)."""
    return dec(value).quantize(RATE_PRECISION, rounding=ROUND_HALF_UP)


def ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    """Safe division returning ``Decimal(0)`` when the denominator is zero.

    A margin rate on a zero-revenue month is meaningless, never a crash: the
    caller marks the month as incomplete instead.
    """
    if denominator == 0:
        return Decimal(0)
    return (numerator / denominator).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def positive(value: Decimal) -> Decimal:
    """``max(0, value)`` — used for over-quota hours (spec 12.3)."""
    return value if value > 0 else Decimal(0)


@dataclass(frozen=True, slots=True)
class Money:
    """An amount with its currency.

    Kept deliberately small: analytical tables store plain decimals, this
    wrapper only guards mixed-currency arithmetic at the edges (AWS bills in
    USD, contracts in EUR).
    """

    amount: Decimal
    currency: str = DEFAULT_CURRENCY

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", money(self.amount))

    def _check(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatch(f"{self.currency} vs {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount - other.amount, self.currency)

    def scale(self, factor: Decimal) -> Money:
        return Money(self.amount * dec(factor), self.currency)

    def is_zero(self) -> bool:
        return self.amount == 0

    def as_decimal(self) -> Decimal:
        return self.amount
