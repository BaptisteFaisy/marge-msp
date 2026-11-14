"""Clause accuracy (R3) and the local extractor that feeds it (spec 13.1)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from generator.build import generate
from marge.domain import Contract, ContractStatus
from marge.eval.clause_accuracy import clause_accuracy, contract_key
from marge.eval.local_extractor import extract_contract, extract_fields


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("contracts")
    generate(out)
    return out


def _contracts(root: Path) -> list[Contract]:
    return [
        extract_contract(root / "contracts" / f"{stem}.txt", "c-001", ContractStatus.VALIDATED)
        for stem in ("ctr-001-v1", "ctr-004-v1", "ctr-007-v1")
    ]


def test_extractor_reads_the_scalar_fields_of_a_contract(generated):
    fields = extract_fields((generated / "contracts" / "ctr-001-v1.txt").read_text("utf-8"))
    assert fields.customer_name == "CALDER LOGISTICS SAS"
    assert fields.start_date == date(2024, 1, 11)
    assert fields.monthly_subscription == Decimal("5000.00")
    assert fields.extra_hour_rate == Decimal("110.00")
    assert fields.included_hours_per_month == Decimal("60.00")
    assert fields.currency == "EUR"
    assert fields.covered_accounts_or_resources == 40


def test_extractor_keeps_the_scope_lists_whole(generated):
    fields = extract_fields((generated / "contracts" / "ctr-001-v1.txt").read_text("utf-8"))
    assert len(fields.services_included) >= 6
    assert len(fields.exclusions) >= 5
    assert len(fields.sla_commitments) == 3
    assert all(item.subject and item.target for item in fields.sla_commitments)


def test_extractor_flags_the_ambiguous_clause_and_only_that_one(generated):
    ambiguous = extract_fields((generated / "contracts" / "ctr-007-v1.txt").read_text("utf-8"))
    clean = extract_fields((generated / "contracts" / "ctr-004-v1.txt").read_text("utf-8"))
    assert "ambiguous_clause" in ambiguous.spans
    assert "raisonnable" in ambiguous.spans["ambiguous_clause"].quote
    assert "ambiguous_clause" not in clean.spans


def test_extractor_reads_a_table_layout_contract(generated):
    fields = extract_fields((generated / "contracts" / "ctr-004-v1.txt").read_text("utf-8"))
    assert fields.customer_name == "MARCHAND DISTRIBUTION SARL"
    assert fields.monthly_subscription == Decimal("2900.00")


def test_contract_key_matches_the_expected_json_keys(generated):
    contract = _contracts(generated)[0]
    assert contract_key(contract) == "ctr-001-v1"


def _ctr001_expected() -> list[dict]:
    """The hand-written ground truth of ctr-001-v1 (R3)."""
    return [
        {
            "contract_id": "ctr-001",
            "version": 1,
            "customer_name": "CALDER LOGISTICS SAS",
            "start_date": "2024-01-11",
            "end_date": "2027-01-10",
            "renewal_terms": "Tacite reconduction pour une période de 12 mois",
            "termination_notice": "3 mois",
            "monthly_subscription": "5000.00",
            "currency": "EUR",
            "included_hours_per_month": "60.00",
            "extra_hour_rate": "110.00",
            "services_included": [
                "Supervision 24/7 de l'infrastructure",
                "Sauvegarde et restauration des données",
                "Patch management des systèmes d'exploitation",
                "Gestion des incidents d'infrastructure",
                "Gestion des accès et des comptes",
                "Optimisation des coûts AWS",
                "Supervision des sauvegardes et test de restauration trimestriel",
            ],
            "exclusions": [
                "les développements applicatifs et la modification du code du Client",
                "la formation des équipes du Client",
                "l'achat de matériel et de licences tierces",
                "les projets de migration applicative",
                "les audits de sécurité applicative",
            ],
            "service_hours": "24 h sur 24, 7 jours sur 7",
            "sla_commitments": [
                {"subject": "Prise en charge d'un incident critique", "target": "30 minutes, 24 h sur 24"},
                {"subject": "Disponibilité de la plateforme supervisée", "target": "99,5 % par mois"},
                {"subject": "Restauration d'une sauvegarde", "target": "4 heures ouvrées"},
            ],
            "penalties": (
                "2 % de l'abonnement mensuel par incident critique pris en charge au-delà du délai "
                "de l'engagement, plafonné à 15 % de l'abonnement mensuel."
            ),
            "indexation_clause": (
                "Révision annuelle du prix au 1er janvier, sur présentation de l'indice Syntec, "
                "dans la limite de 3 % par an."
            ),
            "covered_accounts_or_resources": 40,
            "ambiguous_clause": False,
        }
    ]


def test_clause_accuracy_passes_on_the_generated_contracts(generated):
    expected = _ctr001_expected()
    score = clause_accuracy(_contracts(generated)[:1], expected)
    assert score.passed is True
    assert score.value == Decimal("1")


def test_clause_accuracy_fails_when_a_field_is_wrong(generated):
    expected = [
        {
            "contract_id": "ctr-001",
            "version": 1,
            "customer_name": "AUTRE CLIENT",
            "monthly_subscription": "1.00",
            "extra_hour_rate": "1.00",
        }
    ]
    score = clause_accuracy(_contracts(generated)[:1], expected)
    assert score.passed is False
    assert "customer_name" in " ".join(score.detail)


def test_clause_accuracy_reports_a_contract_that_was_not_extracted():
    score = clause_accuracy([], [{"contract_id": "ctr-001", "version": 1}])
    assert score.passed is False
    assert any("not extracted" in line for line in score.detail)
