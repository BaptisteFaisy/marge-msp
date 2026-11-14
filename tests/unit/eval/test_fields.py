"""Field comparison: French prose versus canonical values (spec 13.3, R3)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from marge.domain import ContractFields, SlaCommitment
from marge.eval.fields import (
    ANNEX_B_FIELDS,
    ambiguous_flag,
    canonical,
    field_matches,
    mismatched_fields,
    normalise_amount,
    normalise_text,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("4 600,00 EUR HT", "4600.00"),
        ("4600.00", "4600.00"),
        ("110,00 EUR", "110.00"),
        ("60,00 heures", "60.00"),
    ],
)
def test_normalise_amount_reads_french_and_canonical_amounts(raw, expected):
    assert normalise_amount(raw) == expected


def test_normalise_text_folds_accents_and_case():
    assert normalise_text("Pénalités  de Niveau") == "penalites de niveau"


def test_canonical_list_keeps_the_order_of_the_contract():
    assert canonical("exclusions", ("a", "B")) == ("a", "b")


def test_canonical_sla_pairs_subject_and_target():
    pairs = canonical("sla_commitments", [SlaCommitment("Disponibilité", "99,5 %")])
    assert pairs == (("disponibilite", "99,5 %"),)


def test_canonical_dates_keep_the_iso_form():
    assert canonical("start_date", date(2026, 1, 1)) == "2026-01-01"


def test_field_matches_is_true_for_an_equivalent_amount():
    assert field_matches("monthly_subscription", Decimal("4600"), "4600.00")


def test_field_matches_is_false_on_a_different_client_name():
    assert not field_matches("customer_name", "CALDER LOGISTICS SAS", "CALDER LOGISTIC SAS")


def test_mismatched_fields_lists_only_the_wrong_ones():
    fields = ContractFields(
        customer_name="CALDER LOGISTICS SAS",
        start_date=date(2026, 1, 1),
        monthly_subscription=Decimal("4600"),
        currency="EUR",
    )
    expected = {
        "customer_name": "CALDER LOGISTICS SAS",
        "start_date": "2026-01-01",
        "monthly_subscription": "4700.00",
        "currency": "EUR",
    }
    missed = mismatched_fields(fields, expected)
    assert "monthly_subscription" in missed
    assert "customer_name" not in missed
    assert "start_date" not in missed


def test_ambiguous_flag_reads_the_source_passage():
    from marge.domain import SourceSpan

    fields = ContractFields()
    assert ambiguous_flag(fields) is False
    fields.spans["ambiguous_clause"] = SourceSpan(quote="une ampleur raisonnable")
    assert ambiguous_flag(fields) is True


def test_annex_b_fields_cover_the_annex_and_the_ambiguity_marker():
    assert len(ANNEX_B_FIELDS) == 17
    assert ANNEX_B_FIELDS[-1] == "ambiguous_clause"
    assert "indexation_clause" in ANNEX_B_FIELDS
    assert "covered_accounts_or_resources" in ANNEX_B_FIELDS
