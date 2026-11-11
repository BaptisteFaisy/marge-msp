"""Tests for the store layer: SQLite round trip, migrations, serde."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from tests.fakes.builders import golden_client, golden_contract, golden_interventions, golden_rates

from marge.domain import (
    AllocationBasis,
    AwsCost,
    Client,
    Contract,
    ContractFields,
    ContractStatus,
    DecisionStatus,
    Intervention,
    MarginLine,
    Month,
    Settings,
    ToolingCost,
    WorkClass,
    WorkLevel,
)
from marge.store import SqliteStore
from marge.store.migrations import apply_migrations, current_version


@pytest.fixture()
def store(tmp_path):
    db = SqliteStore(tmp_path / "marge.sqlite3")
    yield db
    db.close()


def test_migrations_are_idempotent(tmp_path) -> None:
    store = SqliteStore(tmp_path / "db.sqlite3")
    first = current_version(store._conn)
    second = apply_migrations(store._conn)
    assert first >= 1
    assert second == first
    store.close()


def test_client_round_trip(store: SqliteStore) -> None:
    store.upsert_clients([golden_client()])
    client = store.get_client("c-001")
    assert client is not None
    assert client.name == "Durand Industries"
    assert client.managed_resource_count == 40


def test_list_clients_filters_by_account_manager(store: SqliteStore) -> None:
    store.upsert_clients([Client("c-001", "A", "am-01"), Client("c-002", "B", "am-02")])
    assert [c.client_id for c in store.list_clients("am-02")] == ["c-002"]


def test_contract_round_trip_keeps_decimals(store: SqliteStore) -> None:
    store.save_contract(golden_contract())
    loaded = store.get_contract("ctr-001")
    assert loaded is not None
    assert loaded.fields.monthly_subscription == Decimal("4000.00")
    assert loaded.fields.exclusions[0].startswith("les développements")
    assert loaded.status == ContractStatus.VALIDATED
    assert loaded.fields.end_date is not None


def test_active_contract_ignores_unvalidated(store: SqliteStore) -> None:
    contract = golden_contract()
    contract.status = ContractStatus.EXTRACTED
    store.save_contract(contract)
    assert store.active_contract("c-001", Month.parse("2026-10")) is None


def test_active_contract_respects_effective_date(store: SqliteStore) -> None:
    store.save_contract(golden_contract())
    assert store.active_contract("c-001", Month.parse("2025-12")) is None
    assert store.active_contract("c-001", Month.parse("2026-06")) is not None


def test_interventions_round_trip_and_filters(store: SqliteStore) -> None:
    store.save_interventions(golden_interventions())
    month = Month.parse("2026-10")
    rows = store.list_interventions(month=month, client_id="c-001")
    assert len(rows) == 6
    assert rows[0].level in (WorkLevel.N1, WorkLevel.N2, WorkLevel.N3)
    assert store.list_interventions(month=Month.parse("2026-11")) == []


def test_rates_round_trip(store: SqliteStore) -> None:
    store.save_rates(golden_rates())
    rates = store.list_rates()
    assert len(rates) == 3
    assert {r.level for r in rates} == {WorkLevel.N1, WorkLevel.N2, WorkLevel.N3}
    assert all(isinstance(r.hourly_cost, Decimal) for r in rates)


def test_tooling_and_aws_costs_round_trip(store: SqliteStore) -> None:
    store.save_tooling_costs(
        [ToolingCost("supervision", Decimal("1200"), basis=AllocationBasis.PER_LABOUR_HOUR)]
    )
    store.save_aws_costs(
        [
            AwsCost(
                "111122223333",
                Month.parse("2026-10"),
                Decimal("3000"),
                rebilled_amount=Decimal("3620"),
            )
        ]
    )
    assert store.list_tooling_costs()[0].monthly_cost == Decimal("1200.00")
    assert store.list_aws_costs(Month.parse("2026-10"))[0].resale_margin == Decimal("620.00")


def test_margin_lines_replaced_on_save(store: SqliteStore) -> None:
    month = Month.parse("2026-10")
    store.save_margin_lines("c-001", month, [MarginLine("cost.labour", "x", Decimal("10"), "itsm", "wl-1")])
    store.save_margin_lines("c-001", month, [MarginLine("cost.labour", "y", Decimal("20"), "itsm", "wl-2")])
    lines = store.margin_lines("c-001", month)
    assert len(lines) == 1
    assert lines[0].amount == Decimal("20")


def test_settings_round_trip_and_audit(store: SqliteStore) -> None:
    store.save(Settings(margin_threshold=Decimal("0.25")), "controller-01", "tighten the threshold")
    assert store.load().margin_threshold == Decimal("0.25")
    entries = store.list_entries(entity_kind="settings")
    assert len(entries) == 1
    assert entries[0].author == "controller-01"
    assert entries[0].reason == "tighten the threshold"


def test_classification_round_trip_keeps_class_and_status(store: SqliteStore) -> None:
    from marge.domain import Classification

    store.save_classification(
        Classification(
            intervention_id="wl-001",
            client_id="c-001",
            contract_version=1,
            work_class=WorkClass.OUT_OF_SCOPE,
            confidence=Decimal("0.88"),
            status=DecisionStatus.PENDING,
        )
    )
    rows = store.list_classifications(status="PENDING")
    assert rows[0].work_class == WorkClass.OUT_OF_SCOPE
    assert rows[0].confidence == Decimal("0.88")


def test_serde_keeps_tuple_and_enum_types() -> None:
    from marge.store import serde

    contract = Contract(
        "ctr-x",
        "c-001",
        2,
        ContractFields(services_included=("a", "b")),
        ContractStatus.VALIDATED,
    )
    restored = serde.decode(Contract, serde.encode(contract))
    assert isinstance(restored.fields.services_included, tuple)
    assert restored.fields.services_included == ("a", "b")
    assert restored.version == 2
    assert restored.status == ContractStatus.VALIDATED


def test_intervention_hours_are_decimal(store: SqliteStore) -> None:
    store.save_interventions(
        [
            Intervention(
                intervention_id="wl-x",
                ticket_id="t-x",
                client_id="c-001",
                occurred_on=date(2026, 10, 3),
                category="Supervision",
                level=WorkLevel.N2,
                hours_spent=Decimal("2.5"),
            )
        ]
    )
    assert store.list_interventions()[0].hours_spent == Decimal("2.50")
