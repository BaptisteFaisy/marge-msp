"""The generator modules: determinism, formats and the seeded profiles."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from generator import billing, references
from generator.common import (
    MONTHS,
    SEED,
    french_date,
    french_money,
    month_of,
    write_csv,
    write_json,
)
from generator.pdf import generate_pdf, split_into_pages
from generator.profile_data import CLIENTS, CONTRACTS
from generator.tickets import generate


def test_seed_and_months_are_fixed():
    assert SEED == 20261111
    assert MONTHS == ("2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10")


def test_twelve_clients_and_thirteen_contract_versions():
    assert len(CLIENTS) == 12
    assert len({client.client_id for client in CLIENTS}) == 12
    assert len(CONTRACTS) == 13
    assert len({spec.contract_id for spec in CONTRACTS}) == 12


def test_every_client_has_an_account_manager_and_resources():
    for client in CLIENTS:
        assert client.account_manager_id.startswith("am-")
        assert client.managed_resource_count > 0
        assert client.onboarded_on < date(2026, 5, 1)


def test_every_client_alias_is_unique_per_source():
    seen = set()
    for client in CLIENTS:
        for source, source_id, _variant in client.aliases:
            assert (source, source_id) not in seen
            seen.add((source, source_id))


def test_ticket_generation_is_deterministic():
    first = generate(CLIENTS)
    second = generate(CLIENTS)
    assert [row["intervention_id"] for row in first.rows] == [row["intervention_id"] for row in second.rows]
    assert first.total_hours == second.total_hours
    assert len(first.labels) == 150


def test_ticket_generation_covers_six_months_and_leaves_hours_unassigned():
    dataset = generate(CLIENTS)
    months = {month_of(date.fromisoformat(row["occurred_on"])) for row in dataset.rows}
    assert months == set(MONTHS)
    assert dataset.unassigned >= 20
    assert any(not row["customer_ref"] for row in dataset.rows)


def test_ticket_durations_are_decimal_hours():
    dataset = generate(CLIENTS)
    for row in dataset.rows[:200]:
        assert "." in row["hours_spent"]
        assert Decimal(row["hours_spent"]) >= Decimal("0.25")


def test_aws_costs_cover_every_client_and_the_tooling_accounts():
    export = billing.build(CLIENTS)
    accounts = {row[0] for row in export.cost_rows if row[5] == "CLIENT_ACCOUNT"}
    assert len(accounts) == 12
    tooling = {row[0] for row in export.cost_rows if row[5] == "MSP_TOOLING_ACCOUNT"}
    assert len(tooling) == 2
    assert len(export.cost_rows) == (12 + 2) * len(MONTHS)


def test_fx_covers_every_month_with_a_usd_eur_rate():
    export = billing.build(CLIENTS)
    assert [row[0] for row in export.fx_rows] == list(MONTHS)
    assert all(row[1:] == ("USD", "EUR") or row[2] == "EUR" for row in export.fx_rows)


def test_rates_carry_the_july_change():
    tables = references.build(CLIENTS)
    n1 = [row for row in tables.rates if row[0] == "N1"]
    assert n1 == [("N1", "50.00", "2026-01-01", "EUR"), ("N1", "52.50", "2026-07-01", "EUR")]


def test_tooling_covers_the_four_allocation_bases():
    tables = references.build(CLIENTS)
    bases = {row[2] for row in tables.tooling}
    assert bases == {"PER_CLIENT", "PER_ACCOUNT", "PER_MANAGED_RESOURCE", "PER_LABOUR_HOUR"}


def test_invoices_carry_a_subscription_for_every_client_month():
    tables = references.build(CLIENTS)
    subscriptions = [row for row in tables.invoices if row[3] == "SUBSCRIPTION"]
    assert len(subscriptions) == 12 * len(MONTHS)


def test_penalties_are_only_for_the_seeded_clients():
    tables = references.build(CLIENTS)
    assert {row[0] for row in tables.penalties} == {"c-001", "c-002", "c-006", "c-008"}


def test_pdf_generator_produces_a_valid_document():
    data = generate_pdf("Article 1 — Objet\nLe présent contrat est conclu.")
    assert data.startswith(b"%PDF-1.4")
    assert data.rstrip().endswith(b"%%EOF")
    assert b"Helvetica" in data


def test_pdf_generator_splits_long_text_into_pages():
    pages = split_into_pages("\n".join(f"ligne {index}" for index in range(120)))
    assert len(pages) == 3
    assert sum(len(page) for page in pages) == 120


def test_french_formatting_helpers():
    assert french_date(date(2026, 5, 1)) == "1er mai 2026"
    assert french_date(date(2026, 5, 4)) == "4 mai 2026"
    assert french_money(4600) == "4 600,00 EUR"


def test_csv_writer_uses_unix_endings_and_no_quote_noise(tmp_path):
    path = tmp_path / "x.csv"
    write_csv(path, ("a", "b"), [(1, 2), (3, 4)])
    assert path.read_text(encoding="utf-8") == "a,b\n1,2\n3,4\n"


def test_json_writer_keeps_the_keys_in_order(tmp_path):
    path = tmp_path / "x.json"
    write_json(path, {"b": 1, "a": 2})
    assert path.read_text(encoding="utf-8").strip().startswith('{\n  "b"')
