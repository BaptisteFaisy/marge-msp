"""Cost inputs: rates, tooling, AWS bills, invoices, penalties (spec 12.1-12.2).

Domain layer: standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .enums import AllocationBasis, AwsCostKind, InvoiceKind, WorkLevel
from .money import money
from .periods import Month


@dataclass(frozen=True, slots=True)
class Rate:
    """Loaded hourly cost of a level, effective dated (EF-REF-02)."""

    level: WorkLevel
    hourly_cost: Decimal
    effective_from: date
    currency: str = "EUR"

    def __post_init__(self) -> None:
        object.__setattr__(self, "hourly_cost", money(self.hourly_cost, self.currency))


@dataclass(slots=True)
class ToolingCost:
    """A monthly tool cost and how it is spread over clients (EF-REF-03)."""

    tool: str
    monthly_cost: Decimal
    basis: AllocationBasis = AllocationBasis.PER_LABOUR_HOUR
    client_id: str | None = None
    aws_account_id: str | None = None
    currency: str = "EUR"

    def __post_init__(self) -> None:
        self.monthly_cost = money(self.monthly_cost, self.currency)


@dataclass(slots=True)
class AwsCost:
    """AWS cost of one account for one month (EF-SRC-02)."""

    aws_account_id: str
    month: Month
    cost: Decimal
    kind: AwsCostKind = AwsCostKind.CLIENT_ACCOUNT
    client_id: str | None = None
    rebilled_amount: Decimal = Decimal("0")
    currency: str = "USD"

    def __post_init__(self) -> None:
        self.cost = money(self.cost, self.currency)
        self.rebilled_amount = money(self.rebilled_amount, self.currency)

    @property
    def resale_margin(self) -> Decimal:
        """Amount re-billed to the client minus what it costs the MSP."""
        return self.rebilled_amount - self.cost


@dataclass(slots=True)
class Invoice:
    """An issued invoice line (EF-SRC-04, spec 12.1)."""

    invoice_id: str
    client_id: str
    month: Month
    kind: InvoiceKind
    amount: Decimal
    currency: str = "EUR"
    hours_billed: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        self.amount = money(self.amount, self.currency)


@dataclass(slots=True)
class Penalty:
    """A service level penalty paid to a client (spec 12.2)."""

    client_id: str
    month: Month
    amount: Decimal
    reason: str = ""
    currency: str = "EUR"

    def __post_init__(self) -> None:
        self.amount = money(self.amount, self.currency)
