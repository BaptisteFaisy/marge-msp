"""Calculation versioning (EF-CAL-03).

A change of hourly cost or of allocation rule never rewrites the past without
a trace: every recomputation produces a new version, and past versions stay
readable.

Domain layer: standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime


@dataclass(frozen=True, slots=True)
class CalcVersion:
    """One immutable version of the calculation parameters."""

    version: int
    opened_at: datetime
    author: str
    reason: str
    parameters_fingerprint: str = ""

    @classmethod
    def open(cls, version: int, author: str, reason: str, fingerprint: str = "") -> CalcVersion:
        return cls(
            version=version,
            opened_at=datetime.now(UTC),
            author=author,
            reason=reason,
            parameters_fingerprint=fingerprint,
        )

    @property
    def day(self) -> date:
        return self.opened_at.date()


@dataclass(slots=True)
class VersionHistory:
    """The ordered list of versions, newest last."""

    versions: list[CalcVersion] = field(default_factory=list)

    @property
    def current(self) -> CalcVersion | None:
        return self.versions[-1] if self.versions else None

    @property
    def current_number(self) -> int:
        return self.current.version if self.current else 0

    def next_version(self, author: str, reason: str, fingerprint: str = "") -> CalcVersion:
        created = CalcVersion.open(self.current_number + 1, author, reason, fingerprint)
        self.versions.append(created)
        return created

    def get(self, version: int) -> CalcVersion | None:
        for entry in self.versions:
            if entry.version == version:
                return entry
        return None
