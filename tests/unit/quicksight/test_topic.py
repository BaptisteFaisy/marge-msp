"""The semantic layer: definitions, synonyms, aggregations and joins (spec 14.1)."""

from __future__ import annotations

import pytest

from marge.quicksight import DATASET_NAMES, TOPIC, dataset_by_name
from marge.quicksight.topic import MARGIN_SYNONYMS

EXPECTED_SYNONYMS = (
    "rentabilite",
    "marge",
    "ce que le client rapporte",
    "profit",
    "margin",
)


def test_topic_has_the_three_core_definitions() -> None:
    names = {metric.name for metric in TOPIC.metrics}
    assert {"margin", "effort_hours", "unbilled_hours"} <= names


@pytest.mark.parametrize("synonym", EXPECTED_SYNONYMS)
def test_topic_declares_the_business_synonym(synonym: str) -> None:
    assert synonym in MARGIN_SYNONYMS
    assert any(entry.term == synonym for entry in TOPIC.synonyms)


@pytest.mark.parametrize("synonym", EXPECTED_SYNONYMS)
def test_every_synonym_resolves_to_the_margin_metric(synonym: str) -> None:
    resolved = {entry.term: entry.metric for entry in TOPIC.synonyms}
    assert resolved[synonym] == "margin"


def test_synonyms_are_unique_per_term() -> None:
    terms = [entry.term for entry in TOPIC.synonyms]
    assert len(terms) == len(set(terms))


def test_margin_metric_repeats_the_formula_of_spec_12() -> None:
    margin = TOPIC.metric("margin")
    assert margin.formula == "margin = revenue_total - cost_total"
    assert margin.unit == "EUR"
    assert margin.source_dataset == "marge_client_mois"


def test_margin_rate_is_a_ratio_and_is_not_a_mean_of_rates() -> None:
    rate = TOPIC.metric("margin_rate")
    assert rate.unit == "ratio"
    assert "weighted" in rate.default_aggregation


def test_effort_metric_reports_levels_only() -> None:
    effort = TOPIC.metric("effort_hours")
    assert effort.source_dataset == "effort_client_mois_categorie"
    assert "level" in effort.source_fields


def test_unbilled_metric_repeats_the_formula_of_spec_12_3() -> None:
    unbilled = TOPIC.metric("unbilled_hours")
    assert unbilled.source_dataset == "heures_non_facturees"
    assert "out_of_scope_validated_hours" in unbilled.source_fields
    assert "billed_extra_hours" in unbilled.source_fields


def test_topic_declares_default_aggregations() -> None:
    assert TOPIC.default_aggregations
    joined = " ".join(TOPIC.default_aggregations).lower()
    assert "sum" in joined
    assert "weighted" in joined


def test_topic_joins_cover_the_five_datasets() -> None:
    joined = {join.left for join in TOPIC.joins} | {join.right for join in TOPIC.joins}
    assert joined <= set(DATASET_NAMES)
    assert joined == set(DATASET_NAMES)


def test_every_join_declares_its_keys() -> None:
    for join in TOPIC.joins:
        assert join.on
        assert join.cardinality
        assert join.purpose


def test_metric_source_fields_exist_in_their_dataset() -> None:
    for metric in TOPIC.metrics:
        dataset = dataset_by_name(metric.source_dataset)
        for field in metric.source_fields:
            assert field in dataset.field_names, f"{metric.name}.{field}"


def test_topic_unknown_metric_raises() -> None:
    with pytest.raises(KeyError):
        TOPIC.metric("does-not-exist")
