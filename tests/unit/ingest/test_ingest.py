"""Ingestion tests: PII stripping, FX conversion, unassigned bucket (EF-SRC-*, EF-REF-04)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from marge.domain import AwsCostKind, Month, SourceKind, WorkLevel
from marge.ingest import (
    level_from,
    load_aws_costs,
    load_interventions,
    load_invoices,
    parse_fx,
    strip_personal_data,
)
from marge.match import Alias, MappingResolver

ALIASES = [
    Alias("c-001", SourceKind.ITSM, "CALDER", "Calder"),
    Alias("c-001", SourceKind.BILLING, "111122223333", "calder-logistics-prod"),
    Alias("c-001", SourceKind.INVOICE, "CALDER", "Calder"),
]

ROW = {
    "intervention_id": "wl-001",
    "ticket_id": "t-001",
    "customer_ref": "CALDER",
    "occurred_on": "2026-10-03",
    "category": "Supervision",
    "ticket_type": "incident",
    "level": "N2",
    "engineer_ref": "Jean Dupont",
    "hours_spent": "2.5",
    "description": "Redémarrage du service de supervision",
    "aws_account_id": "111122223333",
    "managed_resource_id": "i-123",
}


def test_personal_data_is_stripped_at_the_door() -> None:
    cleaned = strip_personal_data(ROW)
    assert "engineer_ref" not in cleaned
    assert "Dupont" not in str(cleaned)


def test_level_survives_the_strip() -> None:
    cleaned = strip_personal_data(ROW, level_of=level_from)
    assert cleaned["level"] == "N2"


def test_level_from_accepts_free_form_values() -> None:
    assert level_from("n3") == WorkLevel.N3
    assert level_from("Architecte") == WorkLevel.ARCHITECT
    assert level_from("inconnu") == WorkLevel.N1


def test_intervention_is_resolved_to_the_common_client_id() -> None:
    resolver = MappingResolver(ALIASES, [])
    rows = list(load_interventions([strip_personal_data(ROW)], resolver))
    assert rows[0].client_id == "c-001"
    assert rows[0].level == WorkLevel.N2
    assert rows[0].hours_spent == Decimal("2.50")
    assert rows[0].occurred_on == date(2026, 10, 3)


def test_intervention_without_client_lands_in_the_unassigned_bucket() -> None:
    resolver = MappingResolver(ALIASES, [])
    row = {**ROW, "customer_ref": ""}
    rows = list(load_interventions([row], resolver))
    assert rows[0].client_id is None
    assert rows[0].attributed is False


def test_unknown_customer_ref_is_reported_unresolved() -> None:
    resolver = MappingResolver(ALIASES, [])
    row = {**ROW, "customer_ref": "INCONNU"}
    list(load_interventions([row], resolver))
    assert (SourceKind.ITSM, "INCONNU") in resolver.unresolved()


def test_fx_rates_are_parsed_per_month() -> None:
    rates = parse_fx([{"month": "2026-10", "from": "USD", "to": "EUR", "rate": "0.92"}])
    assert rates[(Month.parse("2026-10"), "USD", "EUR")] == Decimal("0.92")


def test_aws_cost_is_converted_to_the_reporting_currency() -> None:
    resolver = MappingResolver(ALIASES, [])
    rates = parse_fx([{"month": "2026-10", "from": "USD", "to": "EUR", "rate": "0.5"}])
    row = {
        "aws_account_id": "111122223333",
        "month": "2026-10",
        "cost": "1000",
        "currency": "USD",
        "rebilled_amount": "2000",
        "kind": "CLIENT_ACCOUNT",
        "client_ref": "calder-logistics-prod",
    }
    cost = next(iter(load_aws_costs([row], resolver, rates)))
    assert cost.cost == Decimal("500.00")
    assert cost.rebilled_amount == Decimal("1000.00")
    assert cost.resale_margin == Decimal("500.00")
    assert cost.currency == "EUR"
    assert cost.client_id == "c-001"


def test_aws_cost_keeps_its_kind() -> None:
    resolver = MappingResolver(ALIASES, [])
    row = {
        "aws_account_id": "999988887777",
        "month": "2026-10",
        "cost": "95",
        "currency": "EUR",
        "rebilled_amount": "0",
        "kind": "MSP_TOOLING_ACCOUNT",
        "client_ref": "",
    }
    cost = next(iter(load_aws_costs([row], resolver, {})))
    assert cost.kind == AwsCostKind.MSP_TOOLING_ACCOUNT


def test_invoices_are_loaded_with_their_hours() -> None:
    resolver = MappingResolver(ALIASES, [])
    rows = load_invoices(
        [
            {
                "invoice_id": "inv-1",
                "customer_ref": "CALDER",
                "month": "2026-10",
                "kind": "EXTRA_HOURS",
                "amount": "550",
                "hours_billed": "5",
                "currency": "EUR",
            }
        ],
        resolver,
    )
    invoices = list(rows)
    assert invoices[0].hours_billed == Decimal("5")
    assert invoices[0].amount == Decimal("550.00")
