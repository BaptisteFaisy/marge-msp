"""Month arithmetic and effective-dated lookups.

Rates, contracts and allocation rules are all *effective dated*: computing a
past month must use the value in force that month (spec 12.4, EF-CAL-03).

Domain layer: standard library only.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Protocol, TypeVar


class EffectiveDated(Protocol):
    """Anything carrying an ``effective_from`` date."""

    effective_from: date


T = TypeVar("T", bound=EffectiveDated)


@dataclass(frozen=True, slots=True, order=True)
class Month:
    """A calendar month, the grain of every analytical table (Annex A)."""

    year: int
    month: int

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12:
            raise ValueError(f"month out of range: {self.month}")

    @classmethod
    def parse(cls, text: str) -> Month:
        """Parse ``2026-10`` (or ``2026-10-05``, keeping the month)."""
        parts = text.strip().split("-")
        if len(parts) < 2:
            raise ValueError(f"expected YYYY-MM, got {text!r}")
        return cls(int(parts[0]), int(parts[1]))

    @classmethod
    def of(cls, day: date) -> Month:
        return cls(day.year, day.month)

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    def first_day(self) -> date:
        return date(self.year, self.month, 1)

    def last_day(self) -> date:
        return date(self.year, self.month, calendar.monthrange(self.year, self.month)[1])

    def add_months(self, delta: int) -> Month:
        total = (self.year * 12 + (self.month - 1)) + delta
        return Month(total // 12, total % 12 + 1)

    def previous(self) -> Month:
        return self.add_months(-1)

    def next(self) -> Month:
        return self.add_months(1)

    def months_until(self, other: Month) -> int:
        """Signed distance in months (``other - self``)."""
        return (other.year * 12 + other.month) - (self.year * 12 + self.month)

    def contains(self, day: date) -> bool:
        return day.year == self.year and day.month == self.month


def month_range(start: Month, end: Month) -> list[Month]:
    """Inclusive list of months between ``start`` and ``end``."""
    if end.months_until(start) > 0:
        return []
    count = start.months_until(end)
    return [start.add_months(i) for i in range(count + 1)]


def effective_value(entries: Iterable[T], at: date) -> T | None:  # noqa: UP047
    """Return the entry in force on ``at`` (latest ``effective_from <= at``).

    Ties are broken by the order of the iterable, so callers should pass a
    stable, sorted collection.
    """
    chosen: T | None = None
    for entry in entries:
        if entry.effective_from <= at and (chosen is None or entry.effective_from >= chosen.effective_from):
            chosen = entry
    return chosen


def days_between(first: date, second: date) -> int:
    """Absolute number of days between two dates."""
    return abs((second - first).days)
