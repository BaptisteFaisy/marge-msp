"""Client identity matching across the three sources (EF-REF-01, spec 13.3)."""

from __future__ import annotations

from .matcher import MappingResolver
from .normalise import Alias, ClientName, confidence_for, normalise_name, strip_accents
from .proposal import duplicate_ids, propose_matches

__all__ = [
    "Alias",
    "ClientName",
    "MappingResolver",
    "confidence_for",
    "duplicate_ids",
    "normalise_name",
    "propose_matches",
    "strip_accents",
]
