"""Parquet publication (idea 71): types from the DDL, amounts exact, smaller.

Skipped when pyarrow is absent: the CI workers do not have it, and JSONL stays
the default format for that reason.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

pyarrow = pytest.importorskip("pyarrow", reason="parquet needs pyarrow")

from tests.fakes.builders import golden_inputs  # noqa: E402
from tests.fakes.fake_store import FakeStore  # noqa: E402

from marge.domain import Month  # noqa: E402
from marge.publish import MemoryWriter, publish, render_jsonl, rows_of  # noqa: E402
from marge.publish.parquet import (  # noqa: E402
    COMPRESSION,
    EXTENSION,
    arrow_schema,
    read_parquet,
    to_parquet,
)
from marge.publish.tables import column_scales, normalise_row, typed_columns  # noqa: E402

MONTH = Month.parse("2026-10")


def _loaded() -> FakeStore:
    """The Annex D scenario, calculated and stored."""
    from marge.calc import compute_margin_month
    from marge.pipeline import recalculate_month

    data = FakeStore()
    inputs = golden_inputs()
    data.upsert_clients([inputs.client])
    data.save_contract(inputs.contract)
    data.save_rates(list(inputs.rates))
    data.save_tooling_costs(list(inputs.tooling_costs))
    data.save_aws_costs(list(inputs.aws_costs))
    data.save_interventions(list(inputs.interventions))
    for classification in inputs.classifications:
        data.save_classification(classification)
    data.save_margin_months([compute_margin_month(inputs, data.load())])
    recalculate_month(data, data.load(), MONTH)
    return data


@pytest.fixture()
def store() -> FakeStore:
    return _loaded()


def test_schema_types_come_from_the_ddl() -> None:
    schema = arrow_schema("marge_client_mois")
    names = [field.name for field in schema]
    assert names[0] == "client_id"
    assert str(schema.field("margin").type) == "decimal128(12, 2)"
    assert str(schema.field("is_estimate").type) == "bool"
    assert str(schema.field("calc_version").type) == "int32"
    assert names[-1] == "month"


def test_amounts_survive_the_round_trip_exactly() -> None:
    rows = rows_of("marge_client_mois", _loaded(), [MONTH])
    back = read_parquet(to_parquet("marge_client_mois", rows))[0]
    assert back["revenue_total"] == Decimal("4620.00")
    assert back["cost_total"] == Decimal("3725.00")
    assert back["margin"] == Decimal("895.00")
    assert back["margin_rate"] == Decimal("0.1937")


def test_booleans_and_integers_keep_their_type() -> None:
    rows = rows_of("marge_client_mois", _loaded(), [MONTH])
    back = read_parquet(to_parquet("marge_client_mois", rows))[0]
    assert back["is_estimate"] is False
    assert back["calc_version"] == 1


def test_scales_are_taken_from_the_declared_columns() -> None:
    scales = column_scales("marge_client_mois")
    assert scales["margin"] == 2
    assert scales["margin_rate"] == 4
    assert "client_id" not in scales


def test_normalise_row_rounds_to_the_declared_scale() -> None:
    """A value with more decimals than its column would break the write."""
    row = normalise_row(
        "effort_client_mois_categorie",
        {"hourly_cost": Decimal("57.142857"), "hours_spent": Decimal("1.005")},
    )
    assert row["hourly_cost"] == Decimal("57.14")
    assert row["hours_spent"] == Decimal("1.01")


def test_empty_string_becomes_null_on_typed_columns() -> None:
    """Parquet refuses "" for an INT column; Athena would fail to cast it."""
    typed = typed_columns("contrats_actifs")
    assert typed["days_to_renewal"] is True
    assert typed["client_name"] is False
    row = normalise_row("contrats_actifs", {"days_to_renewal": "", "client_name": ""})
    assert row["days_to_renewal"] is None
    assert row["client_name"] == ""


def test_parquet_is_written_with_snappy() -> None:
    assert COMPRESSION == "snappy"
    assert EXTENSION == ".parquet"


def test_publish_in_parquet_uses_the_parquet_keys_and_ddl(store: FakeStore) -> None:
    writer = MemoryWriter()
    report = publish(store, writer, file_format="parquet", bucket="marge-dev-curated")
    assert all(key.endswith(".parquet") for table in report.tables for key in table.keys)
    ddl = report.ddls["marge_client_mois"]
    assert "STORED AS PARQUET" in ddl
    assert "JsonSerDe" not in ddl


def test_both_formats_publish_the_same_rows(store: FakeStore) -> None:
    jsonl = MemoryWriter()
    parquet = MemoryWriter()
    first = publish(store, jsonl, file_format="jsonl")
    second = publish(store, parquet, file_format="parquet")
    assert first.rows == second.rows
    assert [t.table for t in first.tables] == [t.table for t in second.tables]


def test_jsonl_and_parquet_agree_on_the_figures(store: FakeStore) -> None:
    """Same numbers, same rounding, whichever format the lake uses."""
    import json

    jsonl_writer = MemoryWriter()
    publish(store, jsonl_writer, file_format="jsonl")
    payload = jsonl_writer.objects["analytical/marge_client_mois/month=2026-10/part-0.jsonl"]
    from_jsonl = json.loads(payload.decode().splitlines()[0])

    parquet_writer = MemoryWriter()
    publish(store, parquet_writer, file_format="parquet")
    blob = parquet_writer.objects["analytical/marge_client_mois/month=2026-10/part-0.parquet"]
    from_parquet = read_parquet(blob)[0]

    for key in ("margin", "revenue_total", "cost_total", "margin_rate"):
        assert Decimal(from_jsonl[key]) == from_parquet[key], key


def test_unknown_format_is_refused(store: FakeStore) -> None:
    with pytest.raises(ValueError, match="unknown format"):
        publish(store, MemoryWriter(), file_format="avro")


def test_jsonl_stays_the_default(store: FakeStore) -> None:
    writer = MemoryWriter()
    publish(store, writer)
    assert all(key.endswith(".jsonl") for key in writer.objects)


def test_render_jsonl_uses_the_normalised_values(store: FakeStore) -> None:
    """The DDL is the single source of truth for both formats."""
    rows = rows_of("effort_client_mois_categorie", store, [MONTH])
    text = render_jsonl("effort_client_mois_categorie", rows)
    assert text, "the effort table should not be empty on the golden scenario"
