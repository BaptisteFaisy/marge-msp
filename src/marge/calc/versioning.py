"""Calculation versioning (EF-CAL-03).

A change of hourly cost or of allocation rule never rewrites the past without
a trace: every recomputation produces a new version, and past versions stay
readable.

Domain layer: standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

from ..domain import MarginMonth, money


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


@dataclass(frozen=True, slots=True)
class MarginDiff:
    """What changed for one client-month between two calculation versions."""

    client_id: str
    month: str
    margin_before: Decimal
    margin_after: Decimal
    rate_before: Decimal
    rate_after: Decimal
    changed_posts: tuple[str, ...]

    @property
    def margin_delta(self) -> Decimal:
        return money(self.margin_after - self.margin_before)

    @property
    def rate_delta_points(self) -> Decimal:
        return ((self.rate_after - self.rate_before) * 100).quantize(Decimal("0.01"))


POSTS = (
    ("revenue.subscription", lambda m: m.revenue.subscription),
    ("revenue.aws_resale", lambda m: m.revenue.aws_resale_margin),
    ("revenue.extra_hours_billed", lambda m: m.revenue.extra_hours_billed),
    ("revenue.projects", lambda m: m.revenue.projects),
    ("cost.labour", lambda m: m.costs.labour),
    ("cost.tooling", lambda m: m.costs.tooling),
    ("cost.msp_aws", lambda m: m.costs.msp_aws),
    ("cost.penalties", lambda m: m.costs.penalties),
)


def _changed_posts(before: MarginMonth, after: MarginMonth) -> tuple[str, ...]:
    changed = []
    for name, getter in POSTS:
        if getter(before) != getter(after):
            changed.append(name)
    return tuple(changed)


def diff_versions(before: list[MarginMonth], after: list[MarginMonth]) -> list[MarginDiff]:
    """Compare two calculation versions, client-month by client-month.

    EF-CAL-03: changing an hourly rate or an allocation rule must not rewrite
    the past silently. The diff is what makes that promise visible — a reviewer
    sees exactly which post moved, for whom, and by how much.
    """
    index = {(row.client_id, str(row.month)): row for row in before}
    diffs: list[MarginDiff] = []
    for row in after:
        previous = index.get((row.client_id, str(row.month)))
        if previous is None:
            continue
        if previous.margin == row.margin and previous.margin_rate == row.margin_rate:
            continue
        diffs.append(
            MarginDiff(
                client_id=row.client_id,
                month=str(row.month),
                margin_before=previous.margin,
                margin_after=row.margin,
                rate_before=previous.margin_rate,
                rate_after=row.margin_rate,
                changed_posts=_changed_posts(previous, row),
            )
        )
    return sorted(diffs, key=lambda d: abs(d.margin_delta), reverse=True)


def summarise_diff(diffs: list[MarginDiff]) -> dict[str, object]:
    """One-line summary of a version diff, for the API and the portal."""
    total = sum((d.margin_delta for d in diffs), Decimal("0"))
    posts: dict[str, int] = {}
    for diff in diffs:
        for post in diff.changed_posts:
            posts[post] = posts.get(post, 0) + 1
    return {
        "client_months_changed": len(diffs),
        "margin_delta_total": str(money(total)),
        "posts_touched": dict(sorted(posts.items(), key=lambda kv: kv[1], reverse=True)),
    }
