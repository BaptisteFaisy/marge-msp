"""Annex B field plan: what must be read out of a contract (spec 9.2).

The field plan is the single source of truth shared by the Bedrock Data
Automation job, the local deterministic extractor and the evaluation harness.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from ..domain import ContractFields, SlaCommitment

FIELD_PLAN: tuple[str, ...] = (
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
)

MONEY_FIELDS = ("monthly_subscription", "extra_hour_rate")
DATE_FIELDS = ("start_date", "end_date")
NUMBER_FIELDS = ("included_hours_per_month", "covered_accounts_or_resources")
LIST_FIELDS = ("services_included", "exclusions")


@dataclass(frozen=True, slots=True)
class FieldPlanEntry:
    """One field of the plan, with the hint given to the extractor."""

    name: str
    kind: str
    hint: str


FIELD_HINTS: tuple[FieldPlanEntry, ...] = (
    FieldPlanEntry("customer_name", "text", "Raison sociale du client"),
    FieldPlanEntry("start_date", "date", "Date d'effet du contrat"),
    FieldPlanEntry("end_date", "date", "Date de fin"),
    FieldPlanEntry("renewal_terms", "text", "Reconduction tacite ou non, durée"),
    FieldPlanEntry("termination_notice", "text", "Préavis de résiliation"),
    FieldPlanEntry("monthly_subscription", "money", "Abonnement mensuel hors taxes"),
    FieldPlanEntry("currency", "text", "Devise du contrat"),
    FieldPlanEntry("included_hours_per_month", "number", "Heures incluses par mois"),
    FieldPlanEntry("extra_hour_rate", "money", "Tarif horaire hors forfait"),
    FieldPlanEntry("services_included", "list", "Liste des services inclus"),
    FieldPlanEntry("exclusions", "list", "Liste des exclusions"),
    FieldPlanEntry("service_hours", "text", "Plages de service"),
    FieldPlanEntry("sla_commitments", "list", "Engagements de niveau de service"),
    FieldPlanEntry("penalties", "text", "Mode de calcul des pénalités"),
    FieldPlanEntry("indexation_clause", "text", "Clause d'indexation"),
    FieldPlanEntry("covered_accounts_or_resources", "number", "Comptes ou ressources couverts"),
)


def field_plan_payload() -> dict[str, Any]:
    """The plan as Bedrock Data Automation expects it (JSON)."""
    return {
        "name": "marge-contract-fields-v1",
        "documentType": "CONTRACT",
        "fields": [
            {"name": entry.name, "type": entry.kind, "instruction": entry.hint} for entry in FIELD_HINTS
        ],
    }


def parse_money(raw: object) -> Decimal:
    """Parse ``4 000,00 €`` / ``4000.00`` / ``4 000 EUR`` into a Decimal."""
    text = str(raw or "0")
    cleaned = "".join(ch for ch in text if ch.isdigit() or ch in ".,-")
    cleaned = cleaned.replace(".", "").replace(",", ".") if "," in cleaned else cleaned
    try:
        return Decimal(cleaned or "0")
    except InvalidOperation:
        return Decimal("0")


def parse_date(raw: object) -> date | None:
    """Parse ``31/12/2026``, ``2026-12-31`` or ``31 décembre 2026``."""
    import re

    text = str(raw or "").strip()
    if not text:
        return None
    iso = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if iso:
        return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
    french = re.match(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", text)
    if french:
        return date(int(french.group(3)), int(french.group(2)), int(french.group(1)))
    return None


def parse_list(raw: object) -> tuple[str, ...]:
    """A list field: JSON list, bullet list or a single line."""
    if isinstance(raw, (list, tuple)):
        return tuple(str(item).strip() for item in raw if str(item).strip())
    lines = [line.strip(" -•\t") for line in str(raw or "").splitlines()]
    return tuple(line for line in lines if line)


def to_contract_fields(payload: dict[str, Any]) -> ContractFields:
    """Build ``ContractFields`` from an extractor payload (Annex B)."""
    sla_raw = payload.get("sla_commitments") or []
    sla = tuple(
        SlaCommitment(
            subject=str(item.get("subject", "")),
            target=str(item.get("target", "")),
            penalty_rule=str(item.get("penalty_rule", "")),
        )
        if isinstance(item, dict)
        else SlaCommitment(subject=str(item), target="")
        for item in sla_raw
    )
    hours = payload.get("included_hours_per_month")
    covered = payload.get("covered_accounts_or_resources")
    fields = ContractFields(
        customer_name=str(payload.get("customer_name", "") or ""),
        start_date=parse_date(payload.get("start_date")),
        end_date=parse_date(payload.get("end_date")),
        renewal_terms=str(payload.get("renewal_terms", "") or ""),
        termination_notice=str(payload.get("termination_notice", "") or ""),
        monthly_subscription=parse_money(payload.get("monthly_subscription")),
        currency=str(payload.get("currency", "EUR") or "EUR"),
        included_hours_per_month=parse_money(hours) if hours not in (None, "") else None,
        extra_hour_rate=parse_money(payload.get("extra_hour_rate")),
        services_included=parse_list(payload.get("services_included")),
        exclusions=parse_list(payload.get("exclusions")),
        service_hours=str(payload.get("service_hours", "") or ""),
        sla_commitments=sla,
        penalties=str(payload.get("penalties", "") or ""),
        indexation_clause=str(payload.get("indexation_clause", "") or ""),
        covered_accounts_or_resources=int(parse_money(covered)) if covered not in (None, "") else None,
    )
    fields.normalise_amounts()
    return fields


def validate_fields(fields: ContractFields) -> list[str]:
    """Return the list of blocking problems (empty means usable)."""
    problems: list[str] = []
    if not fields.customer_name.strip():
        problems.append("customer_name is empty")
    if fields.start_date is None:
        problems.append("start_date is missing")
    if fields.end_date is None:
        problems.append("end_date is missing")
    if fields.monthly_subscription <= 0:
        problems.append("monthly_subscription must be positive")
    if not fields.services_included:
        problems.append("services_included is empty")
    if not fields.exclusions:
        problems.append("exclusions is empty: the classifier needs the boundary")
    return problems
