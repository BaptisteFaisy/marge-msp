"""The local classifier and the local extractor, used by the harness (spec 13.2)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from marge.domain import (
    Contract,
    ContractFields,
    ContractStatus,
    Intervention,
    SlaCommitment,
    WorkClass,
    WorkLevel,
)
from marge.eval.local_classifier import classify


def _contract(*exclusions: str) -> Contract:
    fields = ContractFields(
        customer_name="DURAND INDUSTRIES SAS",
        services_included=(
            "Supervision 24/7 de l'infrastructure",
            "Sauvegarde et restauration des données",
            "Patch management des systèmes d'exploitation",
            "Mise à jour de version des bases de données",
        ),
        exclusions=exclusions
        or (
            "les développements applicatifs et la modification du code du Client",
            "la formation des équipes du Client",
        ),
        sla_commitments=(SlaCommitment("Disponibilité", "99,5 %"),),
    )
    return Contract(
        contract_id="ctr-001",
        client_id="c-001",
        version=1,
        fields=fields,
        status=ContractStatus.VALIDATED,
    )


def _intervention(category: str, description: str, hours: str = "2.00") -> Intervention:
    return Intervention(
        intervention_id="wl-000001",
        ticket_id="t-000001",
        client_id="c-001",
        occurred_on=date(2026, 10, 5),
        category=category,
        level=WorkLevel.N2,
        hours_spent=Decimal(hours),
        description=description,
    )


def test_classifier_marks_infrastructure_work_as_included():
    result = classify(
        _intervention("Supervision infrastructure", "Contrôle des alertes de supervision"),
        _contract(),
    )
    assert result.work_class == WorkClass.INCLUDED
    assert result.cited_clause.startswith("Services inclus")


def test_classifier_marks_application_development_as_out_of_scope():
    result = classify(
        _intervention("Développement applicatif", "Développement d'un nouvel écran de gestion"),
        _contract(),
    )
    assert result.work_class == WorkClass.OUT_OF_SCOPE
    assert "développements applicatifs" in result.cited_clause


def test_classifier_never_says_out_of_scope_when_the_contract_is_ambiguous():
    """The prudence rule (spec 13.2): a hedged exclusion gives UNCERTAIN."""
    vague = (
        "les maintenances évolutives dont l'ampleur excède le cadre raisonnable d'une intervention courante"
    )
    result = classify(
        _intervention("Maintenance évolutive", "Maintenance évolutive du module de facturation"),
        _contract(vague),
    )
    assert result.work_class == WorkClass.UNCERTAIN
    assert "ambigu" in result.cited_clause


def test_classifier_copies_the_recorded_hours_and_never_invents_them():
    result = classify(_intervention("Sauvegarde", "Contrôle du job de sauvegarde", "1.75"), _contract())
    assert result.billable_hours == Decimal("1.75")


def test_classifier_queues_an_out_of_scope_intervention_for_validation():
    result = classify(
        _intervention("Formation utilisateurs", "Formation des utilisateurs au nouvel outil", "3.00"),
        _contract(),
    )
    assert result.needs_human_validation is True
    assert result.status.value == "PENDING"


def test_classifier_does_not_queue_a_ten_minute_out_of_scope_intervention():
    """Under the 15-minute floor the work is counted, not queued (spec 13.2)."""
    result = classify(
        _intervention("Achat de matériel", "Achat de matériel : recherche de fournisseur", "0.10"),
        _contract(),
    )
    assert result.work_class == WorkClass.OUT_OF_SCOPE
    assert result.needs_human_validation is False


def test_classifier_is_prudent_when_no_scope_keyword_is_found():
    result = classify(_intervention("Divers", "Rangement du local technique"), _contract())
    assert result.work_class == WorkClass.UNCERTAIN
    assert result.confidence < Decimal("0.75")


def test_classifier_stays_prudent_when_both_scopes_match():
    result = classify(
        _intervention(
            "Incident infrastructure",
            "Incident applicatif puis développement du correctif dans le code",
        ),
        _contract(),
    )
    assert result.work_class == WorkClass.UNCERTAIN


def test_classifier_works_without_a_contract():
    result = classify(_intervention("Supervision infrastructure", "Contrôle des alertes"), None)
    assert result.work_class == WorkClass.INCLUDED
    assert result.contract_version == 0


@pytest.mark.parametrize("hours", ["0.25", "0.50", "2.00"])
def test_classifier_confidence_stays_a_decimal(hours):
    result = classify(_intervention("Sauvegarde", "Contrôle du job de sauvegarde", hours), _contract())
    assert isinstance(result.confidence, Decimal)
