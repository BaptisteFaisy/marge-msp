"""Offline tests for ``marge.store.athena`` DDL and query generation."""

from __future__ import annotations

import pytest

from marge.quicksight.datasets import DATASET_NAMES, DATASETS, dataset_by_name
from marge.store.athena import (
    ANALYTICAL_TABLE_NAMES,
    ANALYTICAL_TABLES,
    all_analytical_ddls,
    create_external_table_ddl,
    dataset_query,
    margin_recalculation_query,
    validate_identifier,
)


def test_analytical_tables_cover_five_annex_a_tables() -> None:
    assert ANALYTICAL_TABLE_NAMES == (
        "marge_client_mois",
        "effort_client_mois_categorie",
        "heures_non_facturees",
        "contrats_actifs",
        "interventions_a_valider",
    )
    assert ANALYTICAL_TABLE_NAMES == DATASET_NAMES


@pytest.mark.parametrize("spec", ANALYTICAL_TABLES, ids=ANALYTICAL_TABLE_NAMES)
def test_create_external_table_ddl_is_deterministic_parquet(spec) -> None:
    ddl = create_external_table_ddl(spec, database="marge_prod", bucket="msp-curated", prefix="v1")
    assert ddl.startswith(f"CREATE EXTERNAL TABLE IF NOT EXISTS marge_prod.{spec.name} (")
    assert "STORED AS PARQUET" in ddl
    assert f"LOCATION 's3://msp-curated/v1/{spec.name}/'" in ddl
    assert ddl == create_external_table_ddl(spec, database="marge_prod", bucket="msp-curated", prefix="v1")


def test_partitioned_tables_declare_month_partition() -> None:
    ddls = all_analytical_ddls()
    assert len(ddls) == 5
    for name in ("marge_client_mois", "effort_client_mois_categorie", "heures_non_facturees"):
        assert "PARTITIONED BY (\n    month STRING" in ddls[name]
    for name in ("contrats_actifs", "interventions_a_valider"):
        assert "PARTITIONED BY" not in ddls[name]


def test_ddl_columns_match_quicksight_datasets() -> None:
    for spec in ANALYTICAL_TABLES:
        ddl_cols = {c.name for c in spec.columns} | {p.name for p in spec.partition_keys}
        qs_cols = set(dataset_by_name(spec.name).field_names)
        assert ddl_cols == qs_cols


def test_no_person_column_in_analytical_ddls() -> None:
    """ENF-CONF-01: only skill levels are stored, never person identifiers."""
    forbidden = ("engineer", "person", "technician", "staff", "employee")
    for spec in ANALYTICAL_TABLES:
        for col in spec.columns:
            assert not any(word in col.name.lower() for word in forbidden)


def test_quicksight_datasets_reuse_athena_queries() -> None:
    for dataset in DATASETS:
        assert dataset.sql == dataset_query(dataset.name)


@pytest.mark.parametrize("name", DATASET_NAMES)
def test_dataset_query_supports_custom_database(name: str) -> None:
    sql = dataset_query(name, database="marge_staging")
    assert "marge_staging." in sql
    assert "marge." not in sql


def test_dataset_query_unknown_name_raises() -> None:
    with pytest.raises(KeyError):
        dataset_query("unknown_table")


def test_margin_recalculation_query_includes_chapter_12_posts_and_joins() -> None:
    sql = margin_recalculation_query("2026-10", database="marge_dev")
    for expected in (
        "revenue_subscription",
        "revenue_aws_resale",
        "revenue_extra_hours_billed",
        "revenue_projects",
        "cost_labour",
        "cost_tooling",
        "cost_msp_aws",
        "cost_penalties",
        "margin_rate",
        "out_of_scope_validated_hours",
        "coverage",
        "JOIN marge_dev.couts_horaires",
        "LEFT JOIN marge_dev.classements",
        "LEFT JOIN marge_dev.couts_aws",
        "2026-10",
    ):
        assert expected in sql


def test_margin_recalculation_query_optional_client_filter() -> None:
    sql = margin_recalculation_query("2026-10", client_id="c-001")
    assert sql.endswith("WHERE client_id = 'c-001'")


@pytest.mark.parametrize(
    "bad_ident",
    ["marge; DROP TABLE clients", "marge--x", "1bad", "", "marge.prod", "marge'"],
)
def test_validate_identifier_rejects_injection(bad_ident: str) -> None:
    with pytest.raises(ValueError):
        validate_identifier(bad_ident)
    with pytest.raises(ValueError):
        dataset_query("marge_client_mois", database=bad_ident)
    with pytest.raises(ValueError):
        create_external_table_ddl(ANALYTICAL_TABLES[0], database=bad_ident)


@pytest.mark.parametrize(
    ("bad_bucket", "bad_prefix", "bad_month", "bad_client"),
    [
        ("bad_bucket;rm", "ok", "2026-10", "c-001"),
        ("valid-bucket", "ok'; DROP--", "2026-10", "c-001"),
        ("valid-bucket", "ok", "2026-13", "c-001"),
        ("valid-bucket", "ok", "2026-10", "c-001' OR '1'='1"),
    ],
)
def test_athena_builders_reject_unsafe_inputs(
    bad_bucket: str, bad_prefix: str, bad_month: str, bad_client: str
) -> None:
    if bad_bucket != "valid-bucket" or bad_prefix != "ok":
        with pytest.raises(ValueError):
            create_external_table_ddl(ANALYTICAL_TABLES[0], bucket=bad_bucket, prefix=bad_prefix)
    else:
        with pytest.raises(ValueError):
            margin_recalculation_query(bad_month, client_id=bad_client)
