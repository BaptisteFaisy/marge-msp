"""Deterministic local contract extractor (offline stand-in for Bedrock).

The real pipeline reads the PDF with Bedrock Data Automation (spec 13.1). The
CI workers have no credentials, so the harness runs this rule-based reader on
the machine-readable ``.txt`` twin of every contract instead. It only reads
labelled lines — never guesses — so a field missing from the prose shows up as
a miss in the clause accuracy measure (R3).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ..domain import Contract, ContractFields, ContractStatus, SlaCommitment, SourceSpan
from .fields import AMBIGUITY_SPAN, normalise_amount, normalise_text

LABELS: dict[str, str] = {
    "client": "customer_name",
    "date d'effet": "start_date",
    "date de fin": "end_date",
    "reconduction": "renewal_terms",
    "preavis de resiliation": "termination_notice",
    "abonnement mensuel": "monthly_subscription",
    "heures incluses par mois": "included_hours_per_month",
    "tarif horaire hors forfait": "extra_hour_rate",
    "plages de service": "service_hours",
    "penalites": "penalties",
    "clause d'indexation": "indexation_clause",
    "comptes et ressources couverts": "covered_accounts_or_resources",
    "services inclus": "services_included",
    "exclusions": "exclusions",
    "engagements de niveau de service": "sla_commitments",
}
"""French label -> Annex B field. The twelve layouts all carry these labels."""

VAGUE_MARKERS = (
    "raisonnable",
    "substantielle",
    "notable",
    "significative",
    "selon l'ampleur",
    "au cas par cas",
)
"""A contract whose exclusions hedge like this has an ambiguous clause."""

ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _collect(text: str) -> dict[str, list[str]]:
    """Map every labelled value to its field, in document order.

    A table row with an empty first cell continues the field of the previous
    row: that is how the list fields are laid out in the table layout.
    """
    found: dict[str, list[str]] = {}
    pending: str | None = None
    last_field: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            pending = None
            continue
        if line.startswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) < 2:
                continue
            field = LABELS.get(normalise_text(cells[0]))
            value = " | ".join(cells[1:]).strip()
            if field and value:
                found.setdefault(field, []).append(value)
                last_field = field
            elif last_field and value:
                found.setdefault(last_field, []).append(value)
            continue
        if line[0] in "-•" and pending:
            found.setdefault(pending, []).append(line[1:].strip())
            continue
        head, separator, tail = line.partition(":")
        field = LABELS.get(normalise_text(head)) if separator else None
        if field:
            pending = field
            last_field = field
            if tail.strip():
                found.setdefault(field, []).append(tail.strip())
                pending = None
            continue
        pending = None
    return found


def _first(found: dict[str, list[str]], field: str) -> str:
    values = found.get(field) or [""]
    return values[0]


def _as_date(text: str) -> date | None:
    match = ISO_DATE.search(text)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(0))
    except ValueError:
        return None


def _as_decimal(text: str) -> Decimal | None:
    cleaned = normalise_amount(text)
    try:
        return Decimal(cleaned) if cleaned else None
    except (InvalidOperation, ValueError):
        return None


def _as_currency(text: str) -> str:
    for code in ("EUR", "USD", "GBP"):
        if code in text.upper():
            return code
    return "EUR"


def _as_sla(values: list[str]) -> tuple[SlaCommitment, ...]:
    commitments: list[SlaCommitment] = []
    for value in values:
        subject, _, target = value.partition(" — ")
        commitments.append(SlaCommitment(subject=subject.strip(), target=target.strip()))
    return tuple(commitments)


def _ambiguous_passage(exclusions: tuple[str, ...]) -> str | None:
    """The exclusion passage that hedges, if any (spec 19.1)."""
    for exclusion in exclusions:
        if any(marker in normalise_text(exclusion) for marker in VAGUE_MARKERS):
            return exclusion
    return None


def extract_fields(text: str) -> ContractFields:
    """Read every Annex B field out of one contract text."""
    found = _collect(text)
    subscription_text = _first(found, "monthly_subscription")
    quota_text = _first(found, "included_hours_per_month")
    exclusions = tuple(found.get("exclusions", []))
    fields = ContractFields(
        customer_name=_first(found, "customer_name"),
        start_date=_as_date(_first(found, "start_date")),
        end_date=_as_date(_first(found, "end_date")),
        renewal_terms=_first(found, "renewal_terms"),
        termination_notice=_first(found, "termination_notice"),
        monthly_subscription=_as_decimal(subscription_text) or Decimal("0"),
        currency=_as_currency(subscription_text),
        included_hours_per_month=(
            None if "illimite" in normalise_text(quota_text) else _as_decimal(quota_text)
        ),
        extra_hour_rate=_as_decimal(_first(found, "extra_hour_rate")) or Decimal("0"),
        services_included=tuple(found.get("services_included", [])),
        exclusions=exclusions,
        service_hours=_first(found, "service_hours"),
        sla_commitments=_as_sla(found.get("sla_commitments", [])),
        penalties=_first(found, "penalties"),
        indexation_clause=_first(found, "indexation_clause"),
        covered_accounts_or_resources=int(
            re.sub(r"\D", "", _first(found, "covered_accounts_or_resources")) or 0
        ),
    )
    vague = _ambiguous_passage(exclusions)
    if vague is not None:
        fields.spans[AMBIGUITY_SPAN] = SourceSpan(quote=vague)
    return fields


def contract_id_of(path: Path) -> tuple[str, int]:
    """``ctr-011-v2.txt`` -> ``("ctr-011", 2)``."""
    stem = path.stem
    contract_id, _, version = stem.rpartition("-v")
    return contract_id, int(version)


def extract_contract(path: Path, client_id: str, status: ContractStatus) -> Contract:
    """Build the :class:`Contract` of one ``.txt`` document."""
    contract_id, version = contract_id_of(path)
    fields = extract_fields(path.read_text(encoding="utf-8"))
    return Contract(
        contract_id=contract_id,
        client_id=client_id,
        version=version,
        fields=fields,
        status=status,
        document_key=f"contracts/{path.name}",
        effective_from=fields.start_date,
    )
