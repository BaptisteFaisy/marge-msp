"""Comparison of Annex B field values (spec 13.3, R3).

The extracted side is a :class:`marge.domain.ContractFields`; the expected side
is the hand-written ground truth of ``expected/contract_fields.json``. Both are
normalised to a canonical form before comparison, so a French amount
("4 600,00 EUR") and its decimal form ("4600.00") compare equal.

``ambiguous_clause`` is not a field of the frozen domain model: the extractor
records the passage that made it flag the clause, in
``ContractFields.spans["ambiguous_clause"]`` (EF-CTR-02 wants exactly that: the
value shown next to its source passage).
"""

from __future__ import annotations

import unicodedata
from decimal import Decimal, InvalidOperation

ANNEX_B_FIELDS: tuple[str, ...] = (
    "customer_name",
    "start_date",
    "end_date",
    "renewal_terms",
    "termination_notice",
    "monthly_subscription",
    "currency",
    "included_hours_per_month",
    "extra_hour_rate",
    "services_included",
    "exclusions",
    "service_hours",
    "sla_commitments",
    "penalties",
    "indexation_clause",
    "covered_accounts_or_resources",
    "ambiguous_clause",
)
"""The Annex B fields plus the ``ambiguous_clause`` marker (spec 19.1)."""

AMBIGUITY_SPAN = "ambiguous_clause"


def strip_accents(text: str) -> str:
    """``Pénalités`` becomes ``Penalites``."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def normalise_text(value: object) -> str:
    """Lower-case, accent-free, whitespace-collapsed text."""
    if value is None:
        return ""
    text = strip_accents(str(value)).lower()
    return " ".join(text.replace("\u00a0", " ").replace("\u202f", " ").split())


def normalise_amount(value: object) -> str:
    """Canonical decimal string: ``"4 600,00 EUR HT"`` -> ``"4600.00"``."""
    if value is None:
        return ""
    text = str(value)
    for token in ("EUR", "USD", "€", "HT", "heures", "heure", "%"):
        text = text.replace(token, " ")
    text = text.replace("\u00a0", " ").replace("\u202f", " ").replace(" ", "")
    text = text.replace(",", ".")
    cleaned = "".join(char for char in text if char.isdigit() or char in ".-")
    try:
        return f"{Decimal(cleaned):.2f}"
    except (InvalidOperation, ValueError):
        return normalise_text(value)


def normalise_list(items: object) -> tuple[str, ...]:
    """Ordered, accent-free list of texts (order is part of the contract)."""
    if not items:
        return ()
    return tuple(normalise_text(item) for item in items)


def normalise_sla(items: object) -> tuple[tuple[str, str], ...]:
    """SLA commitments as ``(subject, target)`` pairs, normalised."""
    pairs: list[tuple[str, str]] = []
    for item in items or ():
        if isinstance(item, dict):
            pairs.append((normalise_text(item.get("subject")), normalise_text(item.get("target"))))
        else:
            pairs.append(
                (
                    normalise_text(getattr(item, "subject", "")),
                    normalise_text(getattr(item, "target", "")),
                )
            )
    return tuple(pairs)


def ambiguous_flag(fields: object) -> bool:
    """True when the extractor found the passage that makes a clause ambiguous."""
    spans = getattr(fields, "spans", None) or {}
    return AMBIGUITY_SPAN in spans


def canonical(field: str, value: object) -> object:
    """Canonical representation of one field value, whatever its origin."""
    if field in ("monthly_subscription", "extra_hour_rate", "included_hours_per_month"):
        return "" if value in (None, "") else normalise_amount(value)
    if field in ("services_included", "exclusions"):
        return normalise_list(value)
    if field == "sla_commitments":
        return normalise_sla(value)
    if field in ("start_date", "end_date"):
        return "" if value is None else str(value)[:10]
    if field == "covered_accounts_or_resources":
        return "" if value is None else str(int(value))
    if field == "currency":
        return normalise_text(value).upper()
    return normalise_text(value)


def field_matches(field: str, extracted: object, expected: object) -> bool:
    """True when the extracted value is the expected one for ``field``."""
    if field == "ambiguous_clause":
        return bool(extracted) == bool(expected)
    return canonical(field, extracted) == canonical(field, expected)


def mismatched_fields(extracted: object, expected: dict) -> list[str]:
    """Names of the Annex B fields the extraction got wrong."""
    return [
        field
        for field in ANNEX_B_FIELDS
        if not field_matches(
            field,
            ambiguous_flag(extracted) if field == "ambiguous_clause" else getattr(extracted, field, None),
            expected.get(field),
        )
    ]
