"""Publishing the Annex A tables: layout, columns, types, idempotence."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from tests.fakes.builders import golden_inputs
from tests.fakes.fake_store import FakeStore

from marge.domain import Month
from marge.publish import (
    FILE_FORMAT,
    MemoryWriter,
    columns_of,
    months_of,
    publish,
    render_jsonl,
    rows_of,
    validate_row,
)
from marge.store.athena import ANALYTICAL_TABLES, all_analytical_ddls

TABLE_NAMES = [spec.name for spec in ANALYTICAL_TABLES]


def _loaded_store() -> FakeStore:
    """A store holding the Annex D scenario, already calculated."""
    from marge.calc import compute_effort_slices, compute_hours_summary, compute_margin_month
    from marge.pipeline import recalculate_month

    store = FakeStore()
    inputs = golden_inputs()
    settings = store.load()
    store.upsert_clients([inputs.client])
    store.save_contract(inputs.contract)
    store.save_rates(list(inputs.rates))
    store.save_tooling_costs(list(inputs.tooling_costs))
    store.save_aws_costs(list(inputs.aws_costs))
    store.save_interventions(list(inputs.interventions))
    for classification in inputs.classifications:
        store.save_classification(classification)
    store.save_margin_months([compute_margin_month(inputs, settings)])
    store.save_hours_summaries([compute_hours_summary(inputs, settings)])
    store.save_effort_slices(compute_effort_slices(inputs, settings))
    recalculate_month(store, settings, Month.parse("2026-10"))
    return store


def test_every_annex_a_table_is_published() -> None:
    writer = MemoryWriter()
    report = publish(_loaded_store(), writer)
    assert [t.table for t in report.tables] == TABLE_NAMES
    assert report.files > 0
    assert report.rows > 0


def test_partitioned_tables_use_the_athena_layout() -> None:
    writer = MemoryWriter()
    publish(_loaded_store(), writer, prefix="analytical")
    margins = [key for key in writer.objects if key.startswith("analytical/marge_client_mois/")]
    assert margins == ["analytical/marge_client_mois/month=2026-10/part-0.jsonl"]


def test_unpartitioned_tables_have_no_month_partition() -> None:
    writer = MemoryWriter()
    publish(_loaded_store(), writer)
    contracts = [key for key in writer.objects if "contrats_actifs" in key]
    assert contracts == ["analytical/contrats_actifs/part-0.jsonl"]


def test_published_keys_match_the_ddl_columns_exactly() -> None:
    writer = MemoryWriter()
    publish(_loaded_store(), writer)
    for name in TABLE_NAMES:
        payload = next(v for k, v in writer.objects.items() if f"/{name}/" in k)
        first = json.loads(payload.decode("utf-8").splitlines()[0])
        assert list(first) == columns_of(name), name


def test_annex_d_figures_survive_the_publication() -> None:
    writer = MemoryWriter()
    publish(_loaded_store(), writer)
    payload = writer.objects["analytical/marge_client_mois/month=2026-10/part-0.jsonl"]
    row = json.loads(payload.decode("utf-8").splitlines()[0])
    assert row["revenue_total"] == "4620.00"
    assert row["cost_total"] == "3725.00"
    assert row["margin"] == "895.00"
    assert row["margin_rate"] == "0.1937"
    assert row["state"] == "COMPLETE"
    assert row["month"] == "2026-10"


def test_amounts_stay_exact_strings_never_floats() -> None:
    """A float would lose cents; the serde coerces the string back to DECIMAL."""
    writer = MemoryWriter()
    publish(_loaded_store(), writer)
    payload = writer.objects["analytical/heures_non_facturees/month=2026-10/part-0.jsonl"]
    row = json.loads(payload.decode("utf-8").splitlines()[0])
    assert row["unbilled_hours"] == "9.00"
    assert row["unbilled_value"] == "990.00"
    assert isinstance(row["unbilled_value"], str)


def test_booleans_and_integers_keep_their_json_type() -> None:
    writer = MemoryWriter()
    publish(_loaded_store(), writer)
    payload = writer.objects["analytical/marge_client_mois/month=2026-10/part-0.jsonl"]
    row = json.loads(payload.decode("utf-8").splitlines()[0])
    assert row["is_estimate"] is False
    assert row["calc_version"] == 1


def test_the_validation_queue_carries_the_cited_clause() -> None:
    writer = MemoryWriter()
    publish(_loaded_store(), writer)
    payload = writer.objects["analytical/interventions_a_valider/part-0.jsonl"]
    rows = [json.loads(line) for line in payload.decode("utf-8").splitlines() if line]
    assert rows, "the pending queue must not be empty"
    assert all(row["decision_status"] == "PENDING" for row in rows)


def test_publishing_twice_overwrites_without_duplicating() -> None:
    writer = MemoryWriter()
    store = _loaded_store()
    first = publish(store, writer)
    second = publish(store, writer)
    assert first.files == second.files
    assert len(writer.objects) == second.files


def test_ddls_match_the_published_format() -> None:
    writer = MemoryWriter()
    report = publish(_loaded_store(), writer, bucket="marge-dev-curated")
    ddl = report.ddls["marge_client_mois"]
    assert FILE_FORMAT == "JSONL"
    assert "org.apache.hive.hcatalog.data.JsonSerDe" in ddl
    assert "s3://marge-dev-curated/analytical/marge_client_mois/" in ddl
    assert "skip.header.line.count" not in ddl


def test_ddls_of_a_plain_call_stay_parquet() -> None:
    """The default is unchanged so an existing Parquet lake keeps working."""
    ddl = all_analytical_ddls(bucket="marge-dev-curated")["marge_client_mois"]
    assert "STORED AS PARQUET" in ddl


def test_months_of_falls_back_to_the_stored_months() -> None:
    store = _loaded_store()
    assert months_of(store, None) == [Month.parse("2026-10")]
    asked = [Month.parse("2026-09"), Month.parse("2026-10")]
    assert months_of(store, asked) == asked


def test_rows_are_complete_for_every_table() -> None:
    store = _loaded_store()
    for name in TABLE_NAMES:
        for row in rows_of(name, store, [Month.parse("2026-10")]):
            assert validate_row(name, row) == [], name


def test_render_jsonl_of_an_empty_table_is_empty() -> None:
    assert render_jsonl("contrats_actifs", []) == ""


def test_publish_reports_the_number_of_rows_per_table() -> None:
    report = publish(_loaded_store(), MemoryWriter())
    by_name = {t.table: t.rows for t in report.tables}
    assert by_name["marge_client_mois"] == 1
    assert by_name["heures_non_facturees"] == 1
    assert by_name["effort_client_mois_categorie"] >= 1


def test_amounts_are_decimal_before_rendering() -> None:
    store = _loaded_store()
    rows = rows_of("marge_client_mois", store, [Month.parse("2026-10")])
    assert isinstance(rows[0]["margin"], Decimal)
    assert rows[0]["margin"] == Decimal("895.00")


def test_publish_needs_no_network(tmp_path) -> None:
    """boto3 must not be imported by the local path (CI workers lack it)."""
    import sys

    before = "boto3" in sys.modules
    publish(_loaded_store(), MemoryWriter())
    if not before:
        assert "boto3" not in sys.modules


def test_unknown_table_is_rejected() -> None:
    with pytest.raises(KeyError):
        rows_of("table_inconnue", FakeStore(), [])
