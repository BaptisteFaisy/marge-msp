"""Interventions and their classification (spec 9.3, 13.2, Annex C).

Domain layer: standard library only. No person is ever stored: only the level
of the engineer who worked (ENF-CONF-01, ENF-CONF-02).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .enums import DecisionStatus, WorkClass, WorkLevel
from .money import hours
from .periods import Month


@dataclass(frozen=True, slots=True)
class Intervention:
    """One ticket intervention with the time spent on it (EF-SRC-01)."""

    intervention_id: str
    ticket_id: str
    client_id: str | None
    occurred_on: date
    category: str
    level: WorkLevel
    hours_spent: Decimal
    description: str = ""
    ticket_type: str = ""
    managed_resource_id: str | None = None
    aws_account_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hours_spent", hours(self.hours_spent))

    @property
    def month(self) -> Month:
        return Month.of(self.occurred_on)

    @property
    def attributed(self) -> bool:
        """True when the hours are attached to a client (EF-REF-04)."""
        return self.client_id is not None and self.client_id != ""


@dataclass(slots=True)
class Classification:
    """Annex C — the structured output of the classification step.

    ``billable_hours`` is copied from the recorded duration by code, never
    produced by the model (Annex C note).
    """

    intervention_id: str
    client_id: str
    contract_version: int
    work_class: WorkClass
    confidence: Decimal
    cited_clause: str = ""
    reason: str = ""
    billable_hours: Decimal = Decimal("0")
    needs_human_validation: bool = False
    decided_by_memory: bool = False
    model_id: str = ""
    classified_at: date | None = None
    status: DecisionStatus = DecisionStatus.PENDING
    decided_by: str | None = None
    decided_at: date | None = None
    decision_reason: str = ""

    def __post_init__(self) -> None:
        self.billable_hours = hours(self.billable_hours)

    @property
    def out_of_scope(self) -> bool:
        return self.work_class == WorkClass.OUT_OF_SCOPE

    @property
    def counts_as_unbilled(self) -> bool:
        """Only human-validated out-of-scope hours count (spec 8.3)."""
        return self.out_of_scope and self.status == DecisionStatus.APPROVED


@dataclass(frozen=True, slots=True)
class CategoryDecision:
    """A remembered human decision for one contract + category (EF-CLS-04)."""

    contract_id: str
    contract_version: int
    category: str
    work_class: WorkClass
    decided_by: str
    decided_at: date
    reason: str = ""

    @property
    def key(self) -> tuple[str, int, str]:
        return (self.contract_id, self.contract_version, self.category)
