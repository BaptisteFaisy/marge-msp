"""The generator produces the canonical files of docs/DATA-FORMATS.md."""

from __future__ import annotations

import csv
import json

import pytest

CANONICAL_FILES = (
    "clients.json",
    "aliases.json",
    "interventions.csv",
    "aws_costs.csv",
    "fx.csv",
    "invoices.csv",
    "rates.csv",
    "tooling.csv",
    "penalties.csv",
    "expected/contract_fields.json",
    "labels/interventions.jsonl",
    "questions/reference_questions.json",
    "manifest.json",
)

CSV_HEADERS = {
    "interventions.csv": [
        "intervention_id",
        "ticket_id",
        "customer_ref",
        "occurred_on",
        "category",
        "ticket_type",
        "level",
        "engineer_ref",
        "hours_spent",
        "description",
        "aws_account_id",
        "managed_resource_id",
    ],
    "aws_costs.csv": [
        "aws_account_id",
        "month",
        "cost",
        "currency",
        "rebilled_amount",
        "kind",
        "managed_resource_count",
        "client_ref",
    ],
    "fx.csv": ["month", "from", "to", "rate"],
    "invoices.csv": [
        "invoice_id",
        "customer_ref",
        "month",
        "kind",
        "amount",
        "hours_billed",
        "currency",
    ],
    "rates.csv": ["level", "hourly_cost", "effective_from", "currency"],
    "tooling.csv": ["tool", "monthly_cost", "basis", "client_id", "aws_account_id", "currency"],
    "penalties.csv": ["client_id", "month", "amount", "reason", "currency"],
}


@pytest.mark.integration
@pytest.mark.parametrize("name", CANONICAL_FILES)
def test_generator_writes_canonical_file(dataset_root, name):
    assert (dataset_root / name).is_file()


@pytest.mark.integration
@pytest.mark.parametrize("name", sorted(CSV_HEADERS))
def test_generator_csv_header_matches_contract(dataset_root, name):
    with (dataset_root / name).open(encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))
    assert header == CSV_HEADERS[name]


@pytest.mark.integration
def test_generator_writes_twelve_contract_versions(dataset_root):
    pdfs = sorted((dataset_root / "contracts").glob("*.pdf"))
    texts = sorted((dataset_root / "contracts").glob("*.txt"))
    assert len(pdfs) == 13
    assert [path.stem for path in pdfs] == [path.stem for path in texts]
    assert "ctr-011-v2" in {path.stem for path in pdfs}


@pytest.mark.integration
def test_generator_manifest_counts_match_the_files(dataset_root):
    manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["seed"] == 20261111
    assert manifest["clients"] == 12
    assert manifest["months"] == 6
    assert (manifest["first_month"], manifest["last_month"]) == ("2026-05", "2026-10")
    assert manifest["contracts"] == 12
    assert manifest["labelled_interventions"] == 150
    assert manifest["reference_questions"] == 20
    assert sum(manifest["interventions_by_month"].values()) == manifest["interventions"]


@pytest.mark.integration
def test_generator_is_deterministic(tmp_path):
    from generator.build import generate

    first = generate(tmp_path / "a")
    second = generate(tmp_path / "b")
    assert first["files"] == second["files"]
    assert first["interventions"] == second["interventions"]
