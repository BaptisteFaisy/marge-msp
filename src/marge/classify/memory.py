"""Remembering human decisions (EF-CLS-04).

A human decision on one work category for one contract version applies to the
following interventions of the same category: the account manager is asked
once, not once per ticket.
"""

from __future__ import annotations

from datetime import date

from ..domain import CategoryDecision, Classification, DecisionStatus, WorkClass
from ..store.base import Store


class DecisionMemory:
    """Read/write access to the remembered category decisions."""

    def __init__(self, store: Store) -> None:
        self._store = store

    def lookup(self, contract_id: str, version: int, category: str) -> CategoryDecision | None:
        return self._store.find_category_decision(contract_id, version, category)

    def remember(self, decision: CategoryDecision) -> None:
        self._store.save_category_decision(decision)

    def remember_from(
        self, classification: Classification, contract_id: str, category: str, author: str
    ) -> CategoryDecision:
        """Store the human decision attached to one validated classification."""
        decision = CategoryDecision(
            contract_id=contract_id,
            contract_version=classification.contract_version,
            category=category,
            work_class=classification.work_class,
            decided_by=author,
            decided_at=classification.decided_at or date.today(),
            reason=classification.decision_reason or classification.reason,
        )
        self.remember(decision)
        return decision

    def apply(self, classification: Classification, contract_id: str, category: str) -> Classification | None:
        """Reuse a past decision for this contract and category, if any."""
        decision = self.lookup(contract_id, classification.contract_version, category)
        if decision is None:
            return None
        classification.work_class = decision.work_class
        classification.decided_by_memory = True
        classification.needs_human_validation = False
        classification.status = DecisionStatus.APPROVED
        classification.decided_by = decision.decided_by
        classification.decided_at = decision.decided_at
        classification.decision_reason = f"reused decision: {decision.reason}"
        return classification


def is_decided(classification: Classification) -> bool:
    return classification.status in (DecisionStatus.APPROVED, DecisionStatus.CORRECTED)


def decided_class(classification: Classification, fallback: WorkClass) -> WorkClass:
    """The class that counts: the human one when decided, else the proposal."""
    return classification.work_class if is_decided(classification) else fallback
