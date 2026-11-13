"""Contract routes: clauses next to source spans, corrections, validation
(EF-CTR-02, EF-CTR-03, EF-VAL-02, EF-TDB-06)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from tests.fakes.fake_store import FakeStore


def test_list_contracts_ok(client: TestClient, hdr) -> None:
    response = client.get("/v1/contracts", headers=hdr("CONTROLLER"))
    assert response.status_code == 200
    ids = {row["contract_id"] for row in response.json()}
    assert ids == {"ctr-001", "ctr-002"}


def test_list_contracts_account_manager_row_filtered(client: TestClient, hdr) -> None:
    response = client.get("/v1/contracts", headers=hdr("ACCOUNT_MANAGER", "am-02"))
    assert response.status_code == 200
    rows = response.json()
    assert [row["contract_id"] for row in rows] == ["ctr-002"]


def test_get_contract_shows_span_next_to_value(client: TestClient, hdr) -> None:
    response = client.get("/v1/contracts/ctr-002", headers=hdr("CONTROLLER"))
    assert response.status_code == 200
    body = response.json()
    assert body["fields"]["monthly_subscription"] == "2500.00"
    span = body["fields"]["spans"]["monthly_subscription"]
    assert "2 500 EUR par mois" in span["quote"]
    assert span["page"] == 1


def test_get_contract_with_version(client: TestClient, hdr) -> None:
    response = client.get("/v1/contracts/ctr-001?version=1", headers=hdr("CONTROLLER"))
    assert response.status_code == 200
    assert response.json()["version"] == 1


def test_get_contract_unknown_returns_404(client: TestClient, hdr) -> None:
    response = client.get("/v1/contracts/ctr-999", headers=hdr("CONTROLLER"))
    assert response.status_code == 404


def test_get_contract_other_clients_forbidden(client: TestClient, hdr) -> None:
    response = client.get("/v1/contracts/ctr-002", headers=hdr("ACCOUNT_MANAGER", "am-01"))
    assert response.status_code == 403


def test_update_fields_changes_value_and_audits(client: TestClient, store: FakeStore, hdr) -> None:
    response = client.put(
        "/v1/contracts/ctr-002/fields",
        headers=hdr("CONTROLLER", "controller-01"),
        json={
            "reason": "PDF shows 2 600 EUR, not 2 500",
            "fields": {"monthly_subscription": "2600"},
        },
    )
    assert response.status_code == 200
    assert response.json()["fields"]["monthly_subscription"] == "2600.00"
    entries = store.list_entries(entity_kind="contract", entity_id="ctr-002")
    assert any(e.action == "update_fields" and e.author == "controller-01" for e in entries)


def test_update_fields_rejects_bad_date(client: TestClient, hdr) -> None:
    response = client.put(
        "/v1/contracts/ctr-002/fields",
        headers=hdr("CONTROLLER"),
        json={"reason": "typo", "fields": {"start_date": "not-a-date"}},
    )
    assert response.status_code == 422


def test_update_fields_forbidden_for_account_manager(client: TestClient, hdr) -> None:
    response = client.put(
        "/v1/contracts/ctr-002/fields",
        headers=hdr("ACCOUNT_MANAGER", "am-02"),
        json={"reason": "x", "fields": {"monthly_subscription": "1"}},
    )
    assert response.status_code == 403


def test_validate_contract_sets_status_and_audits(client: TestClient, store: FakeStore, hdr) -> None:
    response = client.post(
        "/v1/contracts/ctr-002/validate",
        headers=hdr("CONTROLLER", "controller-01"),
        json={"reason": "clauses conformes au PDF"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "VALIDATED"
    assert response.json()["validated_by"] == "controller-01"
    entries = store.list_entries(entity_kind="contract", entity_id="ctr-002")
    assert any(e.action == "validate" for e in entries)
    assert store.get_contract("ctr-002").counts_for_calculation


def test_validate_contract_with_corrections(client: TestClient, hdr) -> None:
    response = client.post(
        "/v1/contracts/ctr-002/validate",
        headers=hdr("CONTROLLER"),
        json={"reason": "ok after fix", "corrections": {"included_hours_per_month": "35"}},
    )
    assert response.status_code == 200
    assert response.json()["fields"]["included_hours_per_month"] == "35.00"


def test_validate_contract_forbidden_for_account_manager(client: TestClient, hdr) -> None:
    response = client.post(
        "/v1/contracts/ctr-002/validate",
        headers=hdr("ACCOUNT_MANAGER", "am-02"),
        json={"reason": "x"},
    )
    assert response.status_code == 403


def test_validate_contract_missing_reason_is_422(client: TestClient, hdr) -> None:
    response = client.post("/v1/contracts/ctr-002/validate", headers=hdr("CONTROLLER"), json={})
    assert response.status_code == 422


def test_contracts_survive_a_persisting_store_round_trip(tmp_path) -> None:
    """Regression: the list route must not 500 after a real store round trip.

    The SQLite and DynamoDB stores both persist through ``serde``; a
    ``dict[str, SourceSpan]`` that came back as plain dicts used to crash the
    serialiser and hide every contract from the controller.
    """
    from decimal import Decimal

    from marge.api import create_app
    from marge.domain import Client, Contract, ContractFields, ContractStatus, SourceSpan
    from marge.store import SqliteStore

    fields = ContractFields(monthly_subscription=Decimal("2500"), extra_hour_rate=Decimal("95"))
    fields.spans["monthly_subscription"] = SourceSpan(quote="2 500 EUR par mois", page=1)
    store = SqliteStore(tmp_path / "marge.sqlite3")
    try:
        store.upsert_clients([Client("c-002", "Dupont Logistics", "am-02")])
        store.save_contract(Contract("ctr-002", "c-002", 1, fields, ContractStatus.EXTRACTED))
        app = TestClient(create_app(store))
        response = app.get("/v1/contracts", headers={"X-Actor-Id": "c", "X-Actor-Role": "CONTROLLER"})
        assert response.status_code == 200
        span = response.json()[0]["fields"]["spans"]["monthly_subscription"]
        assert span["quote"] == "2 500 EUR par mois"
    finally:
        store.close()
