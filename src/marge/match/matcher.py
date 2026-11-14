"""Resolving a source identifier to the common client id (EF-REF-04).

Two layers, in this order:
1. the matches a human APPROVED — the only authoritative source;
2. the raw aliases, so a first load can run before validation (the proposals
   stay PENDING and the portal shows them).
"""

from __future__ import annotations

from collections.abc import Iterable

from ..domain import ClientMatch, DecisionStatus, SourceKind
from .normalise import Alias, normalise_name


class MappingResolver:
    """Resolve ``(source, source_id)`` to a common client id."""

    def __init__(
        self,
        aliases: Iterable[Alias] = (),
        matches: Iterable[ClientMatch] = (),
    ) -> None:
        self._approved: dict[tuple[SourceKind, str], str] = {}
        self._by_name: dict[tuple[SourceKind, str], str] = {}
        self._unresolved: list[tuple[SourceKind, str]] = []
        self._aliases = list(aliases)

        for match in matches:
            if match.status == DecisionStatus.APPROVED:
                self._approved[(match.source, match.source_id.strip().lower())] = match.client_id
        for alias in self._aliases:
            # Three keys per alias: its source id, its normalised name, and the
            # normalised name of its source id (billing accounts are often
            # slugified: "calder-logistics-prod").
            self._by_name[alias.key] = alias.client_id
            self._by_name[(alias.source, normalise_name(alias.name_variant))] = alias.client_id
            self._by_name[(alias.source, normalise_name(alias.source_id))] = alias.client_id

    def resolve(self, source: SourceKind, source_id: str) -> str | None:
        """Return the common client id, or ``None`` and remember the miss."""
        key = (source, (source_id or "").strip().lower())
        if key in self._approved:
            return self._approved[key]
        if key in self._by_name:
            return self._by_name[key]
        by_name = (source, normalise_name(source_id))
        if by_name in self._by_name:
            return self._by_name[by_name]
        if (source, (source_id or "").strip().lower()) not in self._unresolved:
            self._unresolved.append((source, source_id))
        return None

    def unresolved(self) -> list[tuple[SourceKind, str]]:
        """Every identifier that could not be attached to a client."""
        return list(self._unresolved)

    @property
    def approved_count(self) -> int:
        return len(self._approved)

    def with_matches(self, matches: Iterable[ClientMatch]) -> MappingResolver:
        """A new resolver that also knows the approved matches."""
        return MappingResolver(self._aliases, list(matches))
