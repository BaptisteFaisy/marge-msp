"""MCP server tests: JSON-RPC, the three tools and their guards (spec 14.3)."""

from __future__ import annotations

from decimal import Decimal

from tests.fakes.fake_itsm import FakeItsm
from tests.fakes.fake_store import FakeStore

from marge.domain import ActorRole, Client, HoursSummary, Month
from marge.mcp import McpContext, handle_request


def _ctx(role: ActorRole = ActorRole.CONTROLLER, actor: str = "controller-01") -> McpContext:
    store = FakeStore()
    store.upsert_clients([Client("c-001", "Durand Industries", "am-01")])
    return McpContext(store=store, actor_id=actor, role=role, itsm=FakeItsm())


def _call(ctx: McpContext, name: str, arguments: dict) -> dict:
    return handle_request(
        {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": name, "arguments": arguments}},
        ctx,
    )


def _payload(response: dict) -> dict:
    import json

    return json.loads(response["result"]["content"][0]["text"])


def test_initialize_returns_protocol_and_server_info() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"}, _ctx())
    assert response["result"]["protocolVersion"]
    assert response["result"]["serverInfo"]["name"] == "marge-mcp"


def test_tools_list_exposes_the_three_tools() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, _ctx())
    names = {tool["name"] for tool in response["result"]["tools"]}
    assert names == {
        "create_renegotiation_task",
        "draft_extra_billing_proposal",
        "get_margin_breakdown",
    }
    for tool in response["result"]["tools"]:
        assert tool["inputSchema"]["properties"]


def test_unknown_method_is_rejected() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 3, "method": "resources/list"}, _ctx())
    assert response["error"]["code"] == -32601


def test_unknown_tool_is_rejected() -> None:
    response = _call(_ctx(), "delete_everything", {})
    assert response["error"]["code"] == -32602


def test_renegotiation_task_is_created_with_a_dossier() -> None:
    ctx = _ctx()
    payload = _payload(
        _call(ctx, "create_renegotiation_task", {"client_id": "c-001", "reason": "margin down"})
    )
    assert payload["task_id"].startswith("task-c-001")
    assert "source line(s) attached" in payload["dossier"]
    assert "margin down" in payload["dossier"]


def test_second_dossier_for_the_same_client_is_refused() -> None:
    ctx = _ctx()
    _call(ctx, "create_renegotiation_task", {"client_id": "c-001"})
    second = _call(ctx, "create_renegotiation_task", {"client_id": "c-001"})
    assert second["error"]["code"] == -32000
    assert "already open" in second["error"]["message"]


def test_billing_proposal_is_only_a_draft() -> None:
    ctx = _ctx()
    ctx.store.save_hours_summaries(
        [
            HoursSummary(
                client_id="c-001",
                month=Month.parse("2026-10"),
                out_of_scope_validated_hours=Decimal("9"),
                contract_hour_rate=Decimal("110"),
            )
        ]
    )
    payload = _payload(_call(ctx, "draft_extra_billing_proposal", {"client_id": "c-001", "month": "2026-10"}))
    assert payload["status"] == "DRAFT"
    assert payload["sent"] is False
    assert payload["amount"] == "990.00"
    assert ctx.itsm.drafts["c-001"]


def test_breakdown_shows_cost_split_to_the_controller() -> None:
    ctx = _ctx(ActorRole.CONTROLLER)
    from tests.fakes.builders import golden_inputs

    from marge.calc import compute_margin_month

    inputs = golden_inputs()
    ctx.store.save_margin_months([compute_margin_month(inputs, ctx.store.load())])
    payload = _payload(_call(ctx, "get_margin_breakdown", {"client_id": "c-001", "month": "2026-10"}))
    assert payload["margin"] == "895.00"
    assert payload["costs_breakdown"]["labour"] == "3290.00"


def test_breakdown_hides_costs_from_an_account_manager() -> None:
    ctx = _ctx(ActorRole.ACCOUNT_MANAGER, actor="am-01")
    from tests.fakes.builders import golden_inputs

    from marge.calc import compute_margin_month

    ctx.store.save_margin_months([compute_margin_month(golden_inputs(), ctx.store.load())])
    payload = _payload(_call(ctx, "get_margin_breakdown", {"client_id": "c-001", "month": "2026-10"}))
    assert payload["costs_breakdown"] == "restricted"


def test_account_manager_cannot_reach_another_manager_s_client() -> None:
    ctx = _ctx(ActorRole.ACCOUNT_MANAGER, actor="am-99")
    response = _call(ctx, "get_margin_breakdown", {"client_id": "c-001", "month": "2026-10"})
    assert response["error"]["code"] == -32000
    assert "not the account manager" in response["error"]["message"]


def test_unknown_client_raises_a_clean_error() -> None:
    response = _call(_ctx(), "create_renegotiation_task", {"client_id": "c-999"})
    assert response["error"]["code"] == -32000
    assert "unknown client" in response["error"]["message"]


def test_invalid_month_is_rejected() -> None:
    response = _call(_ctx(), "get_margin_breakdown", {"client_id": "c-001", "month": "2026-13"})
    assert response["error"]["code"] == -32000
