"""Contract extraction and validation tests (EF-CTR-01..04, R3, R4)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from marge.contracts import (
    ContractNotUsable,
    LocalTextExtractor,
    extract_fields,
    new_version,
    side_by_side,
    validate_contract,
)
from marge.contracts.schema import FIELD_PLAN, field_plan_payload, parse_money, validate_fields
from marge.domain import ContractStatus

SAMPLE = """CONTRAT DE SERVICES MANAGÉS
Client : Durand Industries
Date d'effet : 01/01/2026
Date de fin : 31/12/2026
Reconduction : tacite, 12 mois
Préavis : 3 mois
Abonnement mensuel : 4 000,00 EUR
Heures incluses : 50
Tarif horaire hors forfait : 110,00 EUR
Plages de service : 24x7
Pénalités : 5 % de l'abonnement par incident majeur
Indexation : INSEE annuelle
Ressources couvertes : 40

Services inclus
- Supervision 24/7 de l'infrastructure
- Sauvegarde et restauration
- Patch management des systèmes

Exclusions
- les développements applicatifs et la modification du code du Client
- la formation des équipes du Client

Engagements
- Disponibilité 99,9 %
"""


def test_field_plan_covers_annex_b() -> None:
    assert len(FIELD_PLAN) == 16
    assert "services_included" in FIELD_PLAN
    assert "extra_hour_rate" in FIELD_PLAN


def test_field_plan_payload_is_serialisable() -> None:
    payload = field_plan_payload()
    assert payload["name"] == "marge-contract-fields-v1"
    assert len(payload["fields"]) == 16


def test_local_extractor_reads_every_key_field() -> None:
    fields = extract_fields(SAMPLE.encode("utf-8"), "ctr-001-v1.pdf")
    assert fields.customer_name == "Durand Industries"
    assert fields.monthly_subscription == Decimal("4000.00")
    assert fields.extra_hour_rate == Decimal("110.00")
    assert fields.included_hours_per_month == Decimal("50.00")
    assert fields.start_date == date(2026, 1, 1)
    assert fields.end_date == date(2026, 12, 31)
    assert fields.covered_accounts_or_resources == 40


def test_local_extractor_keeps_included_and_excluded_lists() -> None:
    fields = extract_fields(SAMPLE.encode("utf-8"))
    assert any("Supervision" in item for item in fields.services_included)
    assert any("développements" in item for item in fields.exclusions)


def test_every_extracted_field_has_its_source_passage() -> None:
    fields = extract_fields(SAMPLE.encode("utf-8"))
    assert fields.spans
    for row in side_by_side(fields):
        assert row.span is not None
        assert row.span.quote


def test_validate_fields_accepts_the_sample() -> None:
    fields = extract_fields(SAMPLE.encode("utf-8"))
    assert validate_fields(fields) == []


def test_validate_fields_reports_missing_exclusions() -> None:
    fields = extract_fields(SAMPLE.encode("utf-8"))
    fields.exclusions = ()
    assert any("exclusions" in problem for problem in validate_fields(fields))


def test_validate_contract_sets_author_date_and_reason() -> None:
    from tests.fakes.builders import golden_contract

    contract = golden_contract()
    contract.status = ContractStatus.EXTRACTED
    validated = validate_contract(contract, "controller-01", "clauses conformes")
    assert validated.status == ContractStatus.VALIDATED
    assert validated.validated_by == "controller-01"
    assert validated.validation_reason == "clauses conformes"


def test_validate_contract_refuses_an_unusable_contract() -> None:
    from tests.fakes.builders import golden_contract

    contract = golden_contract()
    contract.fields.monthly_subscription = Decimal("0")
    with pytest.raises(ContractNotUsable):
        validate_contract(contract, "controller-01")


def test_correction_is_applied_before_validation() -> None:
    from tests.fakes.builders import golden_contract

    contract = golden_contract()
    validated = validate_contract(
        contract, "controller-01", "corrigé", corrections={"monthly_subscription": Decimal("4200")}
    )
    assert validated.fields.monthly_subscription == Decimal("4200.00")


def test_amendment_creates_a_new_version() -> None:
    from tests.fakes.builders import golden_contract

    previous = golden_contract()
    fields = previous.fields
    fields.monthly_subscription = Decimal("4300")
    amended = new_version(previous, fields, "controller-01", "avenant 2026")
    assert amended.version == 2
    assert previous.status == ContractStatus.SUPERSEDED
    assert amended.contract_id == previous.contract_id


def test_parse_money_handles_french_formatting() -> None:
    assert parse_money("4 000,00 €") == Decimal("4000.00")
    assert parse_money("110.5") == Decimal("110.5")


def test_local_extractor_is_deterministic() -> None:
    first = LocalTextExtractor().extract("k", SAMPLE.encode("utf-8"))
    second = LocalTextExtractor().extract("k", SAMPLE.encode("utf-8"))
    assert first.monthly_subscription == second.monthly_subscription
    assert first.spans.keys() == second.spans.keys()
