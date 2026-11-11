"""The exposed route table is locked: chapter 16 plus the declared additions.

Chapter 16 lists the fourteen routes of the validation portal. Three more
families were added deliberately and are declared here so that any new route
still has to be announced in a pull request:

* ``/v1/margins/{client_id}/{month}/why`` — decomposition down to the source
  lines (ENF-TRA-01);
* ``/v1/llm-calls`` and ``/v1/llm-calls/summary`` — the model call log
  (ENF-IA-01..03);
* ``/v1/calc-versions`` and ``/v1/calc-versions/diff`` — calculation versions
  and what a new version changed (EF-CAL-03);
* ``/v1/auth/config`` — how the static portal should authenticate (idea 61).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from marge.api import AuthMode

EXPECTED = {
    ("GET", "/v1/matches"),
    ("POST", "/v1/matches/{match_id}/decision"),
    ("GET", "/v1/contracts"),
    ("GET", "/v1/contracts/{contract_id}"),
    ("PUT", "/v1/contracts/{contract_id}/fields"),
    ("POST", "/v1/contracts/{contract_id}/validate"),
    ("GET", "/v1/classifications"),
    ("POST", "/v1/classifications/{intervention_id}/decision"),
    ("GET", "/v1/rates"),
    ("PUT", "/v1/rates"),
    ("GET", "/v1/allocation-rules"),
    ("PUT", "/v1/allocation-rules"),
    ("GET", "/v1/coverage"),
    ("POST", "/v1/recalculate"),
}


ADDITIONS = {
    ("GET", "/v1/auth/config"),
    ("GET", "/v1/margins/{client_id}/{month}/why"),
    ("GET", "/v1/llm-calls"),
    ("GET", "/v1/llm-calls/summary"),
    ("GET", "/v1/calc-versions"),
    ("GET", "/v1/calc-versions/diff"),
}


def exposed_routes(client: TestClient) -> set[tuple[str, str]]:
    """Route table read from the OpenAPI document (version-independent)."""
    routes: set[tuple[str, str]] = set()
    for path, operations in client.app.openapi()["paths"].items():
        if not path.startswith("/v1"):
            continue
        for method in operations:
            routes.add((method.upper(), path))
    return routes


def test_route_table_matches_chapter_16(client: TestClient) -> None:
    """The fourteen routes of chapter 16 are all present."""
    assert exposed_routes(client) >= EXPECTED


def test_no_undeclared_route(client: TestClient) -> None:
    """Nothing is exposed beyond chapter 16 and the declared additions."""
    assert exposed_routes(client) == EXPECTED | ADDITIONS


PUBLIC_ROUTES = {("GET", "/v1/auth/config")}
"""Bootstrap metadata for the static portal: no secret, deliberately public."""


def test_every_route_requires_authentication(client: TestClient) -> None:
    for method, path in sorted((EXPECTED | ADDITIONS) - PUBLIC_ROUTES):
        concrete = path.replace("{match_id}", "m-001")
        concrete = concrete.replace("{contract_id}", "ctr-001")
        concrete = concrete.replace("{intervention_id}", "wl-001")
        concrete = concrete.replace("{client_id}", "c-001").replace("{month}", "2026-10")
        response = client.request(method, concrete, json={})
        assert response.status_code == 401, f"{method} {concrete} -> {response.status_code}"


def test_dev_mode_is_the_default_auth_mode(client: TestClient) -> None:
    assert client.app.state.auth_mode == AuthMode.DEV


def test_auth_config_is_public_and_declares_the_mode(client: TestClient) -> None:
    """The portal must learn how to authenticate before it can authenticate."""
    response = client.get("/v1/auth/config")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "dev"
    assert body["cognito"] is None
