"""Client identity across the three sources (EF-REF-01, spec 13.3).

Domain layer: standard library only. The model proposes, a human validates:
nothing here ever decides on its own.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

from ..domain import SourceKind

LEGAL_FORMS = (
    "sas",
    "sarl",
    "sa",
    "sasu",
    "eurl",
    "sci",
    "scop",
    "gie",
    "groupe",
    "group",
    "holding",
    "france",
    "inc",
    "ltd",
    "gmbh",
    "srl",
)

NOISE = re.compile(r"[^a-z0-9]+")


def strip_accents(text: str) -> str:
    """Remove diacritics so ``Société`` and ``Societe`` compare equal."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def normalise_name(text: str) -> str:
    """Lowercase, unaccent, drop punctuation and legal forms."""
    cleaned = NOISE.sub(" ", strip_accents(text).lower()).strip()
    words = [word for word in cleaned.split() if word not in LEGAL_FORMS]
    return " ".join(words) or cleaned


def name_key(text: str) -> str:
    """Aggressive key: no spaces at all (``Calder`` -> ``calderind``)."""
    return normalise_name(text).replace(" ", "")


@dataclass(frozen=True, slots=True)
class Alias:
    """How one source names one client (see docs/DATA-FORMATS.md)."""

    client_id: str
    source: SourceKind
    source_id: str
    name_variant: str

    @property
    def key(self) -> tuple[SourceKind, str]:
        return (self.source, self.source_id.strip().lower())


@dataclass(frozen=True, slots=True)
class ClientName:
    """The canonical name of a client, used as the matching anchor."""

    client_id: str
    name: str

    @property
    def normalised(self) -> str:
        return normalise_name(self.name)


def confidence_for(left: str, right: str) -> Decimal:
    """Deterministic confidence for two name variants (0.00 to 1.00)."""
    from difflib import SequenceMatcher

    a, b = name_key(left), name_key(right)
    if not a or not b:
        return Decimal("0.00")
    if a == b:
        return Decimal("1.00")
    ratio = SequenceMatcher(None, a, b).ratio()
    if name_key(left) in name_key(right) or name_key(right) in name_key(left):
        ratio = max(ratio, 0.85)
    return Decimal(f"{ratio:.2f}")
