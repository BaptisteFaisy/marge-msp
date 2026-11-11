"""Lambda handlers: ASGI adapter and the thin wiring (spec 11.2).

Everything runs offline: the store is the in-memory double, the model is the
deterministic local rules, boto3 is never imported.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from tests.fakes.builders import golden_contract, golden_interventions
from tests.fakes.fake_store import FakeStore

from marge.domain import ActorRole, Intervention, Month, Settings, WorkClass, WorkLevel
from marge.lambdas import build_scope, handle, mcp_handler
from marge.lambdas.handlers import _mcp_payload


def _api_event(method: str = "GET", path: str = "/", **extra) -> dict:
    event = {
        "httpMethod": method,
        "path": path,
        "headers": {"Content-Type": "application/json", "X-Actor-Id": "c1", "X-Actor-Role": "CONTROLLER"},
        "queryStringParameters": None,
        "body": None,
        "isBase64Encoded": False,
        "requestContext": {"identity": {"sourceIp": "203.0.113.7"}, "path": path},
    }
    event.update(extra)
    return event


async def _echo_app(scope, receive, send) -> None:
    """A minimal ASGI app echoing the scope back, to test the adapter itself."""
    body = await receive()
    payload = json.dumps(
        {
            "type": scope["type"],
            "method": scope["method"],
            "path": scope["path"],
            "query": scope["query_string"].decode(),
            "headers": {k.decode(): v.decode() for k, v in scope["headers"]},
            "client": scope["client"],
            "body": body["body"].decode(),
        }
    ).encode()
    await send(
        {"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]}
    )
    await send({"type": "http.response.body", "body": payload})


def test_scope_carries_method_path_and_headers() -> None:
    scope = build_scope(_api_event("POST", "/v1/rates"))
    assert scope["type"] == "http"
    assert scope["method"] == "POST"
    assert scope["path"] == "/v1/rates"
    assert (b"x-actor-role", b"CONTROLLER") in scope["headers"]


def test_query_string_is_serialised() -> None:
    event = _api_event(path="/v1/classifications", queryStringParameters={"status": "pending"})
    assert build_scope(event)["query_string"] == b"status=pending"


def test_multi_value_query_and_headers_are_kept() -> None:
    event = _api_event(
        multiValueQueryStringParameters={"month": ["2026-09", "2026-10"]},
        multiValueHeaders={"X-Tag": ["a", "b"]},
    )
    scope = build_scope(event)
    assert b"month=2026-09" in scope["query_string"]
    assert b"month=2026-10" in scope["query_string"]
    assert (b"x-tag", b"b") in scope["headers"]


def test_base64_body_is_decoded() -> None:
    import base64

    raw = base64.b64encode(b'{"a":1}').decode()
    event = _api_event("POST", body=raw, isBase64Encoded=True)
    response = handle(_echo_app, event)
    assert json.loads(response["body"])["body"] == '{"a":1}'


def test_json_response_is_returned_as_text() -> None:
    response = handle(_echo_app, _api_event("GET", "/v1/coverage"))
    assert response["statusCode"] == 200
    assert response["isBase64Encoded"] is False
    assert response["headers"]["content-type"] == "application/json"
    assert json.loads(response["body"])["path"] == "/v1/coverage"


def test_binary_response_is_base64_encoded() -> None:
    async def png_app(scope, receive, send) -> None:
        await send(
            {"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"image/png")]}
        )
        await send({"type": "http.response.body", "body": b"\x89PNG\r\n"})

    response = handle(png_app, _api_event("GET", "/logo.png"))
    assert response["isBase64Encoded"] is True
    import base64

    assert base64.b64decode(response["body"]) == b"\x89PNG\r\n"


def test_mcp_payload_accepts_a_raw_jsonrpc_event() -> None:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    assert _mcp_payload(payload) == payload


def test_mcp_payload_unwraps_an_api_gateway_body() -> None:
    event = _api_event("POST", "/mcp", body=json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}))
    assert _mcp_payload(event)["method"] == "tools/list"


def test_mcp_handler_lists_the_three_tools(monkeypatch) -> None:
    store = FakeStore()
    store.upsert_clients([_client()])
    monkeypatch.setattr("marge.lambdas.handlers._STORE", store, raising=False)
    response = mcp_handler({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {tool["name"] for tool in response["result"]["tools"]}
    assert names == {"create_renegotiation_task", "draft_extra_billing_proposal", "get_margin_breakdown"}


def _client():
    from marge.domain import Client

    return Client("c-001", "Durand Industries", "am-01")


def test_classify_pending_through_the_pipeline_stays_offline() -> None:
    """The Lambda classification path must run with the local rules too."""
    from marge.classify.bedrock import LocalRuleModel
    from marge.classify.service import classify
    from marge.pipeline.nightly import classify_pending

    store = FakeStore()
    store.upsert_clients([_client()])
    store.save_contract(golden_contract())
    store.save_interventions(golden_interventions())
    model = LocalRuleModel()
    classified, _, queued = classify_pending(
        store,
        Settings(),
        Month.parse("2026-10"),
        lambda iv, ct: classify(iv, ct, model, Settings()),
    )
    assert classified == 6
    assert queued >= 1
    rows = store.list_classifications()
    assert any(row.work_class == WorkClass.OUT_OF_SCOPE for row in rows)


def test_intervention_level_is_preserved_for_the_handler() -> None:
    intervention = Intervention(
        "wl-1", "t-1", "c-001", date(2026, 10, 1), "Supervision", WorkLevel.N3, Decimal("2")
    )
    assert intervention.level is WorkLevel.N3
    assert ActorRole("CONTROLLER") is ActorRole.CONTROLLER
