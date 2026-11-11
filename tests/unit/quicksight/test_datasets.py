"""The five datasets of Annex A must be complete and consistent."""

from __future__ import annotations

import pytest

from marge.quicksight import DATASET_NAMES, DATASETS, dataset_by_name
from marge.quicksight.topic import TOPIC

EXPECTED_NAMES = (
    "marge_client_mois",
    "effort_client_mois_categorie",
    "heures_non_facturees",
    "contrats_actifs",
    "interventions_a_valider",
)


def test_datasets_count_is_five() -> None:
    assert len(DATASETS) == 5
    assert DATASET_NAMES == EXPECTED_NAMES


@pytest.mark.parametrize("name", EXPECTED_NAMES)
def test_dataset_has_grain_fields_and_keys(name: str) -> None:
    dataset = dataset_by_name(name)
    assert dataset.grain
    assert dataset.fields
    assert dataset.keys


@pytest.mark.parametrize("name", EXPECTED_NAMES)
def test_dataset_fields_are_typed_and_documented(name: str) -> None:
    dataset = dataset_by_name(name)
    for field in dataset.fields:
        assert field.name
        assert field.data_type in {
            "string",
            "decimal",
            "integer",
            "boolean",
            "date",
        }
        assert field.description


@pytest.mark.parametrize("name", EXPECTED_NAMES)
def test_dataset_keys_are_declared_fields(name: str) -> None:
    dataset = dataset_by_name(name)
    for key in dataset.keys:
        assert key in dataset.field_names


@pytest.mark.parametrize("name", EXPECTED_NAMES)
def test_dataset_has_athena_query(name: str) -> None:
    dataset = dataset_by_name(name)
    assert dataset.sql.strip()
    assert "SELECT" in dataset.sql.upper()
    assert "marge." in dataset.sql


@pytest.mark.parametrize("name", EXPECTED_NAMES)
def test_dataset_has_requirement_reference(name: str) -> None:
    assert dataset_by_name(name).requirement


def test_dataset_field_names_are_unique() -> None:
    for dataset in DATASETS:
        assert len(set(dataset.field_names)) == len(dataset.field_names)


def test_dataset_unknown_name_raises() -> None:
    with pytest.raises(KeyError):
        dataset_by_name("does-not-exist")


def test_margin_dataset_carries_revenue_and_cost_posts() -> None:
    """The revenue and cost posts of spec 12.1 and 12.2 must be there."""
    dataset = dataset_by_name("marge_client_mois")
    expected = {
        "revenue_subscription",
        "revenue_aws_resale",
        "revenue_extra_hours_billed",
        "revenue_projects",
        "cost_labour",
        "cost_tooling",
        "cost_msp_aws",
        "cost_penalties",
        "margin",
        "margin_rate",
        "coverage",
        "is_estimate",
        "account_manager_id",
    }
    assert expected <= set(dataset.field_names)


def test_effort_dataset_is_split_by_category_and_level() -> None:
    dataset = dataset_by_name("effort_client_mois_categorie")
    assert dataset.keys == ("client_id", "month", "category", "level")
    assert {"hours_spent", "labour_cost", "ticket_count", "work_class"} <= set(dataset.field_names)


def test_unbilled_dataset_carries_hours_and_value() -> None:
    dataset = dataset_by_name("heures_non_facturees")
    assert {
        "out_of_scope_validated_hours",
        "over_quota_hours",
        "billed_extra_hours",
        "unbilled_value",
        "state",
    } <= set(dataset.field_names)


def test_contracts_dataset_carries_renewal_horizon() -> None:
    dataset = dataset_by_name("contrats_actifs")
    assert {"end_date", "days_to_renewal", "margin_rate_six_months", "trend"} <= set(dataset.field_names)


def test_interventions_dataset_carries_cited_clause() -> None:
    dataset = dataset_by_name("interventions_a_valider")
    assert {"proposed_class", "cited_clause", "confidence"} <= set(dataset.field_names)


def test_no_person_field_in_any_dataset() -> None:
    """ENF-CONF-01 and ENF-CONF-02: only levels, never a named person."""
    forbidden = ("engineer", "person", "technician", "staff", "employee")
    for dataset in DATASETS:
        for field in dataset.fields:
            assert not any(word in field.name.lower() for word in forbidden)


def test_every_dataset_is_referenced_by_the_topic() -> None:
    assert set(TOPIC.datasets) == set(DATASET_NAMES)
