"""Pipeline reports (spec 8.2, 8.3, 8.4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ..domain import Month


@dataclass(slots=True)
class LoadReport:
    """What one ingestion step brought in."""

    source: str
    month: Month
    rows: int = 0
    resolved: int = 0
    unresolved: int = 0
    unattributed_hours: Decimal = Decimal("0")
    notes: list[str] = field(default_factory=list)

    @property
    def resolution_rate(self) -> Decimal:
        if self.rows == 0:
            return Decimal("1")
        return Decimal(self.resolved) / Decimal(self.rows)


@dataclass(slots=True)
class NightlyReport:
    """Outcome of the nightly run (spec 8.2)."""

    month: Month
    loads: list[LoadReport] = field(default_factory=list)
    classified: int = 0
    reused_decisions: int = 0
    queued_for_validation: int = 0
    clients_recalculated: int = 0
    margins_written: int = 0
    coverage_percent: Decimal = Decimal("0")
    duration_seconds: Decimal = Decimal("0")
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AccountManagerQueue:
    """Out-of-scope and uncertain work waiting for one account manager."""

    account_manager_id: str
    client_ids: tuple[str, ...]
    intervention_ids: tuple[str, ...]
    hours: Decimal
    value: Decimal


@dataclass(slots=True)
class WeeklyReport:
    """Outcome of the weekly validation round (spec 8.3)."""

    generated_on: str
    queues: list[AccountManagerQueue] = field(default_factory=list)
    pending_total: int = 0
    hours_total: Decimal = Decimal("0")
    value_total: Decimal = Decimal("0")


@dataclass(slots=True)
class MonthlyReport:
    """Outcome of the monthly review run (spec 8.4)."""

    month: Month
    review_text: str
    recipients: tuple[str, ...] = ()
    stored_at: str = ""
    figures: dict[str, str] = field(default_factory=dict)
