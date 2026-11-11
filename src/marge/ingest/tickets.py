"""Ticket and worklog loading (EF-SRC-01, spec 17).

The loader is the only place where a person's identity could enter the
system, and it removes it: ``engineer_ref`` is replaced by the skill level at
the door (ENF-CONF-01, ENF-CONF-02). Nothing downstream can see a name.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable, Iterable, Iterator
from datetime import date
from decimal import Decimal, InvalidOperation

from ..domain import Intervention, SourceKind, WorkLevel
from ..match import MappingResolver

PERSON_FIELDS = ("engineer_ref", "engineer", "assignee", "agent_name", "user_name")
LEVEL_ALIASES = {
    "n1": WorkLevel.N1,
    "n2": WorkLevel.N2,
    "n3": WorkLevel.N3,
    "architecte": WorkLevel.ARCHITECT,
    "architect": WorkLevel.ARCHITECT,
}


def strip_personal_data(
    row: dict[str, str], level_of: Callable[[str], WorkLevel] | None = None
) -> dict[str, str]:
    """Remove every person field, keeping the level the person implies."""
    cleaned = {key: value for key, value in row.items() if key not in PERSON_FIELDS}
    if level_of is not None:
        raw_level = row.get("level") or row.get("engineer_ref") or ""
        cleaned["level"] = level_of(raw_level).value
    return cleaned


def level_from(raw: str) -> WorkLevel:
    """Map a free-form level (or an engineer reference) to a ``WorkLevel``."""
    key = (raw or "").strip().lower()
    if key in LEVEL_ALIASES:
        return LEVEL_ALIASES[key]
    for alias, level in LEVEL_ALIASES.items():
        if key.startswith(alias):
            return level
    return WorkLevel.N1


def read_csv(text: str) -> list[dict[str, str]]:
    """Read a CSV with header into a list of dicts."""
    return list(csv.DictReader(io.StringIO(text)))


def parse_hours(raw: str) -> Decimal:
    """Parse a duration; an unreadable duration is zero, never a crash."""
    try:
        return Decimal((raw or "0").replace(",", ".").strip())
    except InvalidOperation:
        return Decimal("0")


def parse_date(raw: str) -> date:
    return date.fromisoformat((raw or "").strip()[:10])


def to_intervention(
    row: dict[str, str], resolver: MappingResolver, source: SourceKind = SourceKind.ITSM
) -> Intervention:
    """Build one ``Intervention`` from one CSV row."""
    customer_ref = (row.get("customer_ref") or "").strip()
    client_id = resolver.resolve(source, customer_ref) if customer_ref else None
    return Intervention(
        intervention_id=row["intervention_id"].strip(),
        ticket_id=(row.get("ticket_id") or "").strip(),
        client_id=client_id,
        occurred_on=parse_date(row.get("occurred_on", "")),
        category=(row.get("category") or "").strip(),
        level=level_from(row.get("level", "")),
        hours_spent=parse_hours(row.get("hours_spent", "0")),
        description=(row.get("description") or "").strip(),
        ticket_type=(row.get("ticket_type") or "").strip(),
        managed_resource_id=(row.get("managed_resource_id") or None),
        aws_account_id=(row.get("aws_account_id") or None),
    )


def load_interventions(
    rows: Iterable[dict[str, str]],
    resolver: MappingResolver,
    source: SourceKind = SourceKind.ITSM,
) -> Iterator[Intervention]:
    """Turn CSV rows into interventions, dropping the person identifiers."""
    for row in rows:
        yield to_intervention(strip_personal_data(row), resolver, source)
