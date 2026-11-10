"""Audit trail (EF-VAL-02, spec 17).

Every validation, every rate change and every recalculation is traced with
its author, its date and its reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """One immutable line of the audit log."""

    entity_kind: str
    entity_id: str
    action: str
    author: str
    at: datetime
    reason: str = ""
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def now(
        cls,
        entity_kind: str,
        entity_id: str,
        action: str,
        author: str,
        reason: str = "",
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> AuditEntry:
        return cls(
            entity_kind=entity_kind,
            entity_id=entity_id,
            action=action,
            author=author,
            at=datetime.now(UTC),
            reason=reason,
            before=before or {},
            after=after or {},
        )

    @property
    def day(self) -> date:
        return self.at.date()


@dataclass(slots=True)
class ValidationRecord:
    """The human decision attached to any model proposal (ENF-IA-02)."""

    entity_kind: str
    entity_id: str
    decision: str
    author: str
    decided_at: datetime
    reason: str = ""
    corrected_value: dict[str, Any] = field(default_factory=dict)
