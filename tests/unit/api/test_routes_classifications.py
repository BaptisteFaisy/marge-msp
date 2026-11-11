"""Classification review routes (EF-CLS-03, EF-CLS-04, EF-VAL-02, EF-TDB-06)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from tests.fakes.fake_store import FakeStore


def test_list_pending_classifications(client: TestClient, hdr) -> None:
    response = client.get("/v1/classifications?status=pending", headers=hdr("ACCOUNT_MANAGER", "am-02"))
    assert response.status_code == 200
    rows = response.json()
    assert {row["intervention_id"] for row in rows} == {"wl-101", "wl-102"}
    assert all(row["status"] == "PENDING" for row in rows)


def test_list_classifications_status_case_insensitive(client: TestClient, hdr) -> None:
    response = client.get("/v1/classifications?status=PENDING", headers=hdr("CONTROLLER"))
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_list_classifications_row_filtered_for_account_manager(client: TestClient, hdr) -> None:
    response = client.get("/v1/classifications", headers=hdr("ACCOUNT_MANAGER", "am-01"))
    assert response.status_code == 200
    assert response.json() == []


def test_list_classifications_includes_intervention_context(client: TestClient, hdr) -> None:
    response = client.get("/v1/classifications?status=pending", headers=hdr("CONTROLLER"))
    rows = {row["intervention_id"]: row for row in response.json()}
    assert rows["wl-101"]["ticket_id"] == "t-2001"
    assert rows["wl-101"]["category"] == "Developpement specifique"
    assert rows["wl-101"]["level"] == "N2"
    assert rows["wl-101"]["billable_hours"] == "4.00"


def test_list_classifications_bad_month_is_422(client: TestClient, hdr) -> None:
    response = client.get("/v1/classifications?month=10-2026", headers=hdr("CONTROLLER"))
    assert response.status_code == 422


def test_list_classifications_month_filter(client: TestClient, hdr) -> None:
    response = client.get("/v1/classifications?month=2026-10", headers=hdr("CONTROLLER"))
    assert response.status_code == 200
    assert len(response.json()) == 2
    response = client.get("/v1/classifications?month=2026-09", headers=hdr("CONTROLLER"))
    assert response.json() == []


def test_decide_classification_approve_and_audit(client: TestClient, store: FakeStore, hdr) -> None:
    response = client.post(
        "/v1/classifications/wl-101/decision",
        headers=hdr("ACCOUNT_MANAGER", "am-02"),
        json={"decision": "APPROVED", "reason": "application work, out of scope"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"
    entries = store.list_entries(entity_kind="classification", entity_id="wl-101")
    assert len(entries) == 1
    assert entries[0].author == "am-02"
    assert entries[0].reason == "application work, out of scope"


def test_approved_out_of_scope_counts_as_unbilled(client: TestClient, store: FakeStore, hdr) -> None:
    client.post(
        "/v1/classifications/wl-101/decision",
        headers=hdr("ACCOUNT_MANAGER", "am-02"),
        json={"decision": "APPROVED", "reason": "confirmed"},
    )
    saved = store.classifications["wl-101"]
    assert saved.counts_as_unbilled


def test_decide_classification_correct_changes_work_class(client: TestClient, hdr) -> None:
    response = client.post(
        "/v1/classifications/wl-102/decision",
        headers=hdr("ACCOUNT_MANAGER", "am-02"),
        json={
            "decision": "CORRECTED",
            "reason": "this is standard supervision",
            "corrected_value": {"work_class": "IN_SCOPE"},
        },
    )
    assert response.status_code == 200
    assert response.json()["work_class"] == "IN_SCOPE"
    assert response.json()["status"] == "CORRECTED"


def test_decide_classification_correct_invalid_class_is_422(client: TestClient, hdr) -> None:
    response = client.post(
        "/v1/classifications/wl-102/decision",
        headers=hdr("ACCOUNT_MANAGER", "am-02"),
        json={
            "decision": "CORRECTED",
            "reason": "typo",
            "corrected_value": {"work_class": "MAYBE"},
        },
    )
    assert response.status_code == 422


def test_decide_classification_discard(client: TestClient, hdr) -> None:
    response = client.post(
        "/v1/classifications/wl-102/decision",
        headers=hdr("ACCOUNT_MANAGER", "am-02"),
        json={"decision": "REJECTED", "reason": "internal rework, not client work"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"


def test_decide_classification_remembers_category(client: TestClient, store: FakeStore, hdr) -> None:
    client.post(
        "/v1/classifications/wl-101/decision",
        headers=hdr("ACCOUNT_MANAGER", "am-02"),
        json={"decision": "APPROVED", "reason": "confirmed"},
    )
    memory = store.find_category_decision("ctr-002", 1, "Developpement specifique")
    assert memory is not None
    assert memory.decided_by == "am-02"


def test_decide_classification_unknown_returns_404(client: TestClient, hdr) -> None:
    response = client.post(
        "/v1/classifications/wl-999/decision",
        headers=hdr("CONTROLLER"),
        json={"decision": "APPROVED", "reason": "x"},
    )
    assert response.status_code == 404


def test_decide_classification_other_clients_forbidden(client: TestClient, hdr) -> None:
    response = client.post(
        "/v1/classifications/wl-101/decision",
        headers=hdr("ACCOUNT_MANAGER", "am-01"),
        json={"decision": "APPROVED", "reason": "x"},
    )
    assert response.status_code == 403


def test_decide_classification_pending_is_400(client: TestClient, hdr) -> None:
    response = client.post(
        "/v1/classifications/wl-101/decision",
        headers=hdr("CONTROLLER"),
        json={"decision": "PENDING", "reason": "x"},
    )
    assert response.status_code == 400
