"""Calculation outputs (spec 12.3, Annex A).

These dataclasses are the exact shape of the five analytical tables loaded
into Quick: ``marge_client_mois``, ``effort_client_mois_categorie``,
``heures_non_facturees``, ``contrats_actifs``, ``interventions_a_valider``.

Domain layer: standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .enums import MarginState, UnbilledState, WorkClass, WorkLevel
from .money import hours, money, ratio
from .periods import Month


@dataclass(frozen=True, slots=True)
class RevenueBreakdown:
    """Revenue of one client for one month (spec 12.1)."""

    subscription: Decimal = Decimal("0")
    aws_resale_margin: Decimal = Decimal("0")
    extra_hours_billed: Decimal = Decimal("0")
    projects: Decimal = Decimal("0")

    @property
    def total(self) -> Decimal:
        return money(self.subscription + self.aws_resale_margin + self.extra_hours_billed + self.projects)


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    """Cost of one client for one month (spec 12.2)."""

    labour: Decimal = Decimal("0")
    tooling: Decimal = Decimal("0")
    msp_aws: Decimal = Decimal("0")
    penalties: Decimal = Decimal("0")

    @property
    def total(self) -> Decimal:
        return money(self.labour + self.tooling + self.msp_aws + self.penalties)


@dataclass(frozen=True, slots=True)
class Coverage:
    """Data coverage: hours attached to a client and a contract (EF-ADM-02)."""

    total_hours: Decimal
    attributed_hours: Decimal

    @property
    def value(self) -> Decimal:
        return ratio(self.attributed_hours, self.total_hours)

    @property
    def percent(self) -> Decimal:
        return money(self.value * 100)


@dataclass(slots=True)
class MarginMonth:
    """One row of ``marge_client_mois`` (EF-CAL-01)."""

    client_id: str
    month: Month
    revenue: RevenueBreakdown
    costs: CostBreakdown
    coverage: Coverage
    account_manager_id: str = ""
    calc_version: int = 1
    calculated_at: date | None = None
    state: MarginState = MarginState.COMPLETE
    incomplete_reason: str = ""

    @property
    def margin(self) -> Decimal:
        return money(self.revenue.total - self.costs.total)

    @property
    def margin_rate(self) -> Decimal:
        return ratio(self.margin, self.revenue.total)

    @property
    def is_estimate(self) -> bool:
        return self.state == MarginState.ESTIMATE


@dataclass(frozen=True, slots=True)
class EffortSlice:
    """One row of ``effort_client_mois_categorie`` (EF-CAL-05)."""

    client_id: str
    month: Month
    category: str
    level: WorkLevel
    hours_spent: Decimal
    labour_cost: Decimal
    ticket_count: int
    work_class: WorkClass

    def __post_init__(self) -> None:
        object.__setattr__(self, "hours_spent", hours(self.hours_spent))
        object.__setattr__(self, "labour_cost", money(self.labour_cost))

    @property
    def cost_per_ticket(self) -> Decimal:
        return ratio(self.labour_cost, Decimal(self.ticket_count))


@dataclass(slots=True)
class HoursSummary:
    """Quota consumption and unbilled hours (EF-CAL-02, spec 12.3)."""

    client_id: str
    month: Month
    included_quota: Decimal = Decimal("0")
    consumed_hours: Decimal = Decimal("0")
    out_of_scope_validated_hours: Decimal = Decimal("0")
    billed_extra_hours: Decimal = Decimal("0")
    contract_hour_rate: Decimal = Decimal("0")
    state: UnbilledState = UnbilledState.DETECTED

    @property
    def over_quota_hours(self) -> Decimal:
        return hours(max(Decimal("0"), self.consumed_hours - self.included_quota))

    @property
    def unbilled_hours(self) -> Decimal:
        value = self.out_of_scope_validated_hours + self.over_quota_hours - self.billed_extra_hours
        return hours(max(Decimal("0"), value))

    @property
    def unbilled_value(self) -> Decimal:
        return money(self.unbilled_hours * self.contract_hour_rate)


@dataclass(frozen=True, slots=True)
class RenewalWatch:
    """One row of ``contrats_actifs`` (EF-TDB-04)."""

    client_id: str
    contract_id: str
    contract_version: int
    end_date: date
    days_to_renewal: int
    monthly_subscription: Decimal
    margin_rate_six_months: Decimal
    trend: str = ""

    @property
    def within_horizon(self) -> bool:
        return 0 <= self.days_to_renewal <= 90


@dataclass(frozen=True, slots=True)
class MarginLine:
    """One source line behind a margin figure (ENF-TRA-01)."""

    post: str
    label: str
    amount: Decimal
    source_kind: str
    source_id: str
