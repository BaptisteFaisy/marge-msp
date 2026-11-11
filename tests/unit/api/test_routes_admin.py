"""Administration routes: rates, allocation rules, coverage, recalculation
(EF-REF-02, EF-REF-03, EF-ADM-02, EF-CAL-01..03, ENF-CONF-03)."""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient
from tests.fakes.fake_store import FakeStore

from marge.domain import Month


def test_list_rates_shows_cost_to_controller(client: TestClient, hdr) -> None:
    response = client.get("/v1/rates", headers=hdr("CONTROLLER"))
    assert response.status_code == 200
    costs = {row["level"]: row["hourly_cost"] for row in response.json()}
    assert costs["N1"] == "50.00"


def test_list_rates_redacted_for_account_manager(client: TestClient, hdr) -> None:
    response = client.get("/v1/rates", headers=hdr("ACCOUNT_MANAGER", "am-01"))
    assert response.status_code == 200
    assert all(row["hourly_cost"] == "[CONFIDENTIAL]" for row in response.json())


def test_put_rates_appends_and_audits(client: TestClient, store: FakeStore, hdr) -> None:
    response = client.put(
        "/v1/rates",
        headers=hdr("CONTROLLER", "controller-01"),
        json={
            "reason": "2027 cost review",
            "rates": [{"level": "N1", "hourly_cost": "55.00", "effective_from": "2027-01-01"}],
        },
    )
    assert response.status_code == 200
    assert response.json()["count"] == 1
    costs = {(r.level.value, str(r.effective_from)): r.hourly_cost for r in store.list_rates()}
    assert costs[("N1", "2027-01-01")] == Decimal("55.00")
    entries = store.list_entries(entity_kind="rates")
    assert entries and entries[0].reason == "2027 cost review"


def test_put_rates_forbidden_for_account_manager(client: TestClient, hdr) -> None:
    response = client.put(
        "/v1/rates",
        headers=hdr("ACCOUNT_MANAGER", "am-01"),
        json={"reason": "x", "rates": [{"level": "N1", "hourly_cost": "1", "effective_from": "2027-01-01"}]},
    )
    assert response.status_code == 403


def test_put_rates_invalid_amount_is_422(client: TestClient, hdr) -> None:
    response = client.put(
        "/v1/rates",
        headers=hdr("CONTROLLER"),
        json={
            "reason": "x",
            "rates": [{"level": "N1", "hourly_cost": "abc", "effective_from": "2027-01-01"}],
        },
    )
    assert response.status_code == 422


def test_put_rates_empty_list_is_422(client: TestClient, hdr) -> None:
    response = client.put("/v1/rates", headers=hdr("CONTROLLER"), json={"reason": "x", "rates": []})
    assert response.status_code == 422


def test_list_allocation_rules_ok(client: TestClient, hdr) -> None:
    response = client.get("/v1/allocation-rules", headers=hdr("CONTROLLER"))
    assert response.status_code == 200
    tools = {row["tool"] for row in response.json()}
    assert tools == {"supervision", "backup-dedie"}


def test_allocation_rules_row_filtered_for_account_manager(client: TestClient, hdr) -> None:
    response = client.get("/v1/allocation-rules", headers=hdr("ACCOUNT_MANAGER", "am-01"))
    assert response.status_code == 200
    tools = {row["tool"] for row in response.json()}
    # shared rule stays visible, the rule dedicated to c-002 does not
    assert tools == {"supervision"}


def test_put_allocation_rules_appends_and_audits(client: TestClient, store: FakeStore, hdr) -> None:
    response = client.put(
        "/v1/allocation-rules",
        headers=hdr("ADMINISTRATOR", "admin-01"),
        json={
            "reason": "new backup tool",
            "rules": [
                {"tool": "backup-2027", "monthly_cost": "400", "basis": "PER_CLIENT", "client_id": "c-001"}
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert any(t.tool == "backup-2027" for t in store.list_tooling_costs())
    assert store.list_entries(entity_kind="allocation_rules")


def test_put_allocation_rules_forbidden_for_account_manager(client: TestClient, hdr) -> None:
    response = client.put(
        "/v1/allocation-rules",
        headers=hdr("ACCOUNT_MANAGER", "am-01"),
        json={"reason": "x", "rules": [{"tool": "t", "monthly_cost": "1", "basis": "PER_CLIENT"}]},
    )
    assert response.status_code == 403


def test_coverage_ok(client: TestClient, hdr) -> None:
    response = client.get("/v1/coverage?month=2026-10", headers=hdr("CONTROLLER"))
    assert response.status_code == 200
    body = response.json()
    assert body["total_hours"] == "6.00"
    assert body["attributed_hours"] == "6.00"
    assert body["healthy"] is True


def test_coverage_bad_month_is_422(client: TestClient, hdr) -> None:
    response = client.get("/v1/coverage?month=2026", headers=hdr("CONTROLLER"))
    assert response.status_code == 422


def test_recalculate_writes_golden_margin(
    golden_client_api: TestClient, golden_store: FakeStore, hdr
) -> None:
    response = golden_client_api.post(
        "/v1/recalculate",
        headers=hdr("CONTROLLER", "controller-01"),
        json={"month": "2026-10", "reason": "demo"},
    )
    assert response.status_code == 200
    assert response.json()["calculated_clients"] == 1
    rows = golden_store.list_margin_months(month=None)
    assert len(rows) == 1
    # Annex D golden numbers, recomputed through the API (ENF-IA-01)
    assert rows[0].revenue.total == Decimal("4620.00")
    assert rows[0].costs.total == Decimal("3725.00")
    assert rows[0].margin == Decimal("895.00")


def test_recalculate_writes_hours_and_effort(
    golden_client_api: TestClient, golden_store: FakeStore, hdr
) -> None:
    golden_client_api.post("/v1/recalculate", headers=hdr("CONTROLLER"), json={"month": "2026-10"})
    summaries = golden_store.list_hours_summaries()
    assert summaries[0].unbilled_hours == Decimal("9.00")
    assert summaries[0].unbilled_value == Decimal("990.00")
    assert golden_store.list_effort_slices()
    lines = golden_store.margin_lines("c-001", Month.parse("2026-10"))
    assert lines


def test_recalculate_audits(golden_client_api: TestClient, golden_store: FakeStore, hdr) -> None:
    golden_client_api.post(
        "/v1/recalculate",
        headers=hdr("CONTROLLER", "controller-01"),
        json={"month": "2026-10", "reason": "rate change"},
    )
    entries = golden_store.list_entries(entity_kind="calculation")
    assert len(entries) == 1
    assert entries[0].action == "recalculate"
    assert entries[0].reason == "rate change"


def test_recalculate_bumps_calc_version(golden_client_api: TestClient, golden_store: FakeStore, hdr) -> None:
    golden_client_api.post("/v1/recalculate", headers=hdr("CONTROLLER"), json={"month": "2026-10"})
    second = golden_client_api.post("/v1/recalculate", headers=hdr("CONTROLLER"), json={"month": "2026-10"})
    assert second.json()["calc_version"] == 2
    assert len(golden_store.list_margin_months()) == 2  # EF-CAL-03: past versions stay


def test_recalculate_forbidden_for_account_manager(golden_client_api: TestClient, hdr) -> None:
    response = golden_client_api.post(
        "/v1/recalculate", headers=hdr("ACCOUNT_MANAGER", "am-01"), json={"month": "2026-10"}
    )
    assert response.status_code == 403


def test_recalculate_invalid_month_is_422(golden_client_api: TestClient, hdr) -> None:
    response = golden_client_api.post("/v1/recalculate", headers=hdr("CONTROLLER"), json={"month": "october"})
    assert response.status_code == 422


def test_recalculate_single_client(client: TestClient, store: FakeStore, hdr) -> None:
    response = client.post(
        "/v1/recalculate", headers=hdr("CONTROLLER"), json={"month": "2026-10", "client_id": "c-002"}
    )
    assert response.status_code == 200
    assert response.json()["calculated_clients"] == 1
    rows = store.list_margin_months()
    assert [r.client_id for r in rows] == ["c-002"]
