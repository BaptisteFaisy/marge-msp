"""Client identity match routes (EF-REF-01, EF-VAL-02, EF-TDB-06)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from tests.fakes.fake_store import FakeStore


def test_list_matches_ok(client: TestClient, hdr) -> None:
    response = client.get("/v1/matches", headers=hdr("CONTROLLER"))
    assert response.status_code == 200
    ids = {row["match_id"] for row in response.json()}
    assert ids == {"m-001", "m-002"}


def test_list_matches_pending_only(client: TestClient, hdr) -> None:
    response = client.get("/v1/matches?pending_only=true", headers=hdr("CONTROLLER"))
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_list_matches_account_manager_row_filtered(client: TestClient, hdr) -> None:
    response = client.get("/v1/matches", headers=hdr("ACCOUNT_MANAGER", "am-01"))
    assert response.status_code == 200
    rows = response.json()
    assert [row["match_id"] for row in rows] == ["m-001"]
    assert all(row["client_id"] == "c-001" for row in rows)


def test_decide_match_approves_and_audits(client: TestClient, store: FakeStore, hdr) -> None:
    response = client.post(
        "/v1/matches/m-001/decision",
        headers=hdr("CONTROLLER", "controller-01"),
        json={"decision": "APPROVED", "reason": "same legal name"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"
    assert response.json()["decided_by"] == "controller-01"
    entries = store.list_entries(entity_kind="match", entity_id="m-001")
    assert len(entries) == 1
    assert entries[0].author == "controller-01"
    assert entries[0].reason == "same legal name"


def test_decide_match_reject_records_reason(client: TestClient, store: FakeStore, hdr) -> None:
    response = client.post(
        "/v1/matches/m-002/decision",
        headers=hdr("CONTROLLER"),
        json={"decision": "REJECTED", "reason": "different AWS account"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert store.get_match("m-002").reason == "different AWS account"


def test_decide_match_corrected_moves_client(client: TestClient, hdr) -> None:
    response = client.post(
        "/v1/matches/m-001/decision",
        headers=hdr("CONTROLLER"),
        json={
            "decision": "CORRECTED",
            "reason": "alias belongs to the other client",
            "corrected_value": {"client_id": "c-002"},
        },
    )
    assert response.status_code == 200
    assert response.json()["client_id"] == "c-002"
    assert response.json()["status"] == "CORRECTED"


def test_decide_match_unknown_returns_404(client: TestClient, hdr) -> None:
    response = client.post(
        "/v1/matches/m-999/decision",
        headers=hdr("CONTROLLER"),
        json={"decision": "APPROVED", "reason": "x"},
    )
    assert response.status_code == 404


def test_decide_match_pending_is_rejected(client: TestClient, hdr) -> None:
    response = client.post(
        "/v1/matches/m-001/decision",
        headers=hdr("CONTROLLER"),
        json={"decision": "PENDING", "reason": "x"},
    )
    assert response.status_code == 400


def test_decide_match_missing_reason_is_422(client: TestClient, hdr) -> None:
    response = client.post(
        "/v1/matches/m-001/decision",
        headers=hdr("CONTROLLER"),
        json={"decision": "APPROVED"},
    )
    assert response.status_code == 422


def test_decide_match_other_clients_forbidden(client: TestClient, hdr) -> None:
    response = client.post(
        "/v1/matches/m-002/decision",
        headers=hdr("ACCOUNT_MANAGER", "am-01"),
        json={"decision": "APPROVED", "reason": "x"},
    )
    assert response.status_code == 403


def test_decide_match_unauthenticated(client: TestClient) -> None:
    response = client.post(
        "/v1/matches/m-001/decision",
        json={"decision": "APPROVED", "reason": "x"},
    )
    assert response.status_code == 401
