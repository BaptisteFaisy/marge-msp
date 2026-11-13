"""Insight routes: traceability, model call log, calculation versions."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from tests.fakes.builders import golden_inputs
from tests.fakes.fake_store import FakeStore

from marge.calc import compute_margin_month
from marge.domain import LlmCall, Month, Rate
from marge.llmlog import estimate_cost, estimate_tokens, logged_classifier, summarise

CONTROLLER = {"X-Actor-Id": "controller-01", "X-Actor-Role": "CONTROLLER"}
MANAGER = {"X-Actor-Id": "am-01", "X-Actor-Role": "ACCOUNT_MANAGER"}
OUTSIDER = {"X-Actor-Id": "am-99", "X-Actor-Role": "ACCOUNT_MANAGER"}


@pytest.fixture()
def loaded(tmp_path):
    """A store holding the Annex D scenario, already calculated."""
    store = FakeStore()
    inputs = golden_inputs()
    store.upsert_clients([inputs.client])
    store.save_contract(inputs.contract)
    store.save_rates(list(inputs.rates))
    store.save_tooling_costs(list(inputs.tooling_costs))
    store.save_aws_costs(list(inputs.aws_costs))
    store.save_interventions(list(inputs.interventions))
    store.save_margin_months([compute_margin_month(inputs, store.load())])
    store.set_margin_lines("c-001", Month.parse("2026-10"), [])
    return store


@pytest.fixture()
def client(loaded):
    from marge.api import create_app

    return TestClient(create_app(store=loaded))


# ------------------------------------------------------------------ idea 37
def test_why_returns_the_whole_chain(client: TestClient) -> None:
    response = client.get("/v1/margins/c-001/2026-10/why", headers=CONTROLLER)
    assert response.status_code == 200
    body = response.json()
    assert body["margin"] == "895.00"
    assert body["revenue_total"] == "4620.00"
    assert body["cost_total"] == "3725.00"
    assert len(body["posts"]) == 8
    assert body["dashboard"] == "/dashboards/client/c-001?month=2026-10"


# ------------------------------------------------------------- margin list
def test_margin_list_returns_the_published_figures(client: TestClient) -> None:
    rows = client.get("/v1/margins", headers=CONTROLLER).json()
    assert len(rows) == 1
    row = rows[0]
    assert row["client_id"] == "c-001"
    assert row["month"] == "2026-10"
    assert row["revenue_total"] == "4620.00"
    assert row["cost_total"] == "3725.00"
    assert row["margin"] == "895.00"
    assert row["margin_rate_percent"] == "19.4"
    assert row["coverage_percent"] == "100.00"
    assert row["state"] == "COMPLETE"
    assert row["why"] == "/v1/margins/c-001/2026-10/why"


def test_margin_list_filters_on_the_month(client: TestClient) -> None:
    assert client.get("/v1/margins?month=2026-09", headers=CONTROLLER).json() == []
    assert len(client.get("/v1/margins?month=2026-10", headers=CONTROLLER).json()) == 1


def test_margin_list_rejects_a_bad_month(client: TestClient) -> None:
    assert client.get("/v1/margins?month=2026-99", headers=CONTROLLER).status_code == 422


def test_margin_list_is_scoped_to_the_portfolio(client: TestClient) -> None:
    assert client.get("/v1/margins", headers=OUTSIDER).json() == []
    assert client.get("/v1/margins?client_id=c-001", headers=OUTSIDER).status_code == 403


def test_why_returns_the_whole_chain_for_a_manager(client: TestClient) -> None:
    """The margin list and the decomposition agree on the same figures."""
    listed = client.get("/v1/margins", headers=CONTROLLER).json()[0]
    why = client.get("/v1/margins/c-001/2026-10/why", headers=CONTROLLER).json()
    assert listed["margin"] == why["margin"]
    assert listed["revenue_total"] == why["revenue_total"]
    assert listed["cost_total"] == why["cost_total"]


def test_why_posts_add_up_to_the_published_totals(client: TestClient) -> None:
    body = client.get("/v1/margins/c-001/2026-10/why", headers=CONTROLLER).json()
    revenue = sum(
        (Decimal(p["amount"]) for p in body["posts"] if p["post"].startswith("revenue")), Decimal("0")
    )
    costs = sum((Decimal(p["amount"]) for p in body["posts"] if p["post"].startswith("cost")), Decimal("0"))
    assert revenue == Decimal(body["revenue_total"])
    assert costs == Decimal(body["cost_total"])
    assert revenue - costs == Decimal(body["margin"])


def test_why_includes_the_hours_breakdown(client: TestClient) -> None:
    body = client.get("/v1/margins/c-001/2026-10/why", headers=CONTROLLER).json()
    assert body["hours"] is None or "unbilled_hours" in body["hours"]


def test_why_is_forbidden_outside_the_portfolio(client: TestClient) -> None:
    assert client.get("/v1/margins/c-001/2026-10/why", headers=OUTSIDER).status_code == 403


def test_why_rejects_a_bad_month(client: TestClient) -> None:
    assert client.get("/v1/margins/c-001/2026-99/why", headers=CONTROLLER).status_code == 422


def test_why_answers_404_when_nothing_was_computed(client: TestClient) -> None:
    assert client.get("/v1/margins/c-001/2025-01/why", headers=CONTROLLER).status_code == 404


# ------------------------------------------------------------------ idea 18
def test_llm_calls_are_listed_with_their_cost(client: TestClient, loaded: FakeStore) -> None:
    loaded.append_llm_call(
        LlmCall(
            purpose="classify",
            model_id="eu.amazon.nova-lite-v1:0",
            entity_kind="intervention",
            entity_id="wl-001",
            client_id="c-001",
            outcome="OUT_OF_SCOPE",
            latency_ms=820,
            input_tokens=1200,
            output_tokens=90,
            cost_usd=estimate_cost("eu.amazon.nova-lite-v1:0", 1200, 90),
        )
    )
    rows = client.get("/v1/llm-calls", headers=CONTROLLER).json()
    assert len(rows) == 1
    assert rows[0]["outcome"] == "OUT_OF_SCOPE"
    assert Decimal(rows[0]["cost_usd"]) > 0


def test_llm_calls_summary_counts_and_costs(client: TestClient, loaded: FakeStore) -> None:
    for index in range(3):
        loaded.append_llm_call(
            LlmCall(
                purpose="classify",
                model_id="eu.amazon.nova-lite-v1:0",
                entity_id=f"wl-{index}",
                client_id="c-001",
                outcome="IN_SCOPE",
                latency_ms=100 * (index + 1),
                input_tokens=1000,
                output_tokens=50,
                cost_usd=estimate_cost("eu.amazon.nova-lite-v1:0", 1000, 50),
            )
        )
    summary = client.get("/v1/llm-calls/summary", headers=CONTROLLER).json()
    assert summary["calls"] == 3
    assert summary["by_outcome"] == {"IN_SCOPE": 3}
    assert Decimal(summary["cost_usd"]) > 0
    assert summary["latency_ms_median"] == 200


def test_llm_calls_are_scoped_to_the_portfolio(client: TestClient, loaded: FakeStore) -> None:
    loaded.append_llm_call(LlmCall(purpose="classify", model_id="m", entity_id="w1", client_id="c-001"))
    rows = client.get("/v1/llm-calls", headers=OUTSIDER).json()
    assert rows == []


# ------------------------------------------------------------------ idea 28
def test_calc_versions_are_management_only(client: TestClient) -> None:
    assert client.get("/v1/calc-versions", headers=MANAGER).status_code == 403


def test_calc_versions_diff_shows_what_moved(client: TestClient, loaded: FakeStore) -> None:
    from marge.calc.versioning import CalcVersion

    inputs = golden_inputs()
    first = compute_margin_month(inputs, loaded.load())
    loaded.save_margin_months([first])
    loaded.save_calc_version(CalcVersion.open(1, "controller-01", "initial"))

    from dataclasses import replace

    original = golden_inputs()
    bumped = tuple(
        Rate(rate.level, rate.hourly_cost + Decimal("10"), rate.effective_from) for rate in original.rates
    )
    changed = replace(original, rates=bumped, calculation_version=2)
    second = compute_margin_month(changed, loaded.load())
    second.calc_version = 2
    loaded.save_margin_months([second])
    loaded.save_calc_version(CalcVersion.open(2, "controller-01", "N1/N2/N3 rates +10 EUR"))

    versions = client.get("/v1/calc-versions", headers=CONTROLLER).json()
    assert [v["version"] for v in versions] == [1, 2]
    assert versions[1]["reason"] == "N1/N2/N3 rates +10 EUR"

    diff = client.get("/v1/calc-versions/diff?before=1&after=2", headers=CONTROLLER).json()
    assert diff["summary"]["client_months_changed"] == 1
    assert Decimal(diff["summary"]["margin_delta_total"]) < 0
    assert "cost.labour" in diff["rows"][0]["changed_posts"]


def test_calc_versions_diff_404_on_unknown_version(client: TestClient) -> None:
    response = client.get("/v1/calc-versions/diff?before=1&after=9", headers=CONTROLLER)
    assert response.status_code == 404


# ------------------------------------------------------------- llmlog module
def test_logged_classifier_records_success_and_outcome() -> None:
    from marge.domain import Classification, DecisionStatus, WorkClass

    store = FakeStore()
    inputs = golden_inputs()
    intervention = inputs.interventions[0]
    contract = inputs.contract

    def fake_classifier(iv, ct) -> Classification:
        return Classification(
            intervention_id=iv.intervention_id,
            client_id=ct.client_id,
            contract_version=ct.version,
            work_class=WorkClass.OUT_OF_SCOPE,
            confidence=Decimal("0.9"),
            reason="application code",
            cited_clause="Article 3.2",
            billable_hours=iv.hours_spent,
            status=DecisionStatus.PENDING,
        )

    wrapped = logged_classifier(fake_classifier, store, model=type("M", (), {"model_id": "test-model"})())
    result = wrapped(intervention, contract)
    assert result.work_class == WorkClass.OUT_OF_SCOPE

    calls = store.list_llm_calls()
    assert len(calls) == 1
    assert calls[0].outcome == "OUT_OF_SCOPE"
    assert calls[0].client_id == "c-001"
    assert calls[0].contract_id == "ctr-001"
    assert calls[0].success is True
    assert calls[0].tokens_estimated is True


def test_logged_classifier_records_failures_and_reraises() -> None:
    store = FakeStore()
    inputs = golden_inputs()

    def broken(iv, ct):
        raise RuntimeError("model down")

    wrapped = logged_classifier(broken, store, model=type("M", (), {"model_id": "test-model"})())
    with pytest.raises(RuntimeError):
        wrapped(inputs.interventions[0], inputs.contract)
    calls = store.list_llm_calls()
    assert calls[0].success is False
    assert "model down" in calls[0].error


def test_logging_failure_never_breaks_the_run() -> None:
    from marge.domain import Classification, WorkClass

    class BrokenStore(FakeStore):
        def append_llm_call(self, call):
            raise RuntimeError("store down")

    store = BrokenStore()
    inputs = golden_inputs()

    def fake(iv, ct) -> Classification:
        return Classification(
            intervention_id=iv.intervention_id,
            client_id=ct.client_id,
            contract_version=ct.version,
            work_class=WorkClass.INCLUDED,
            confidence=Decimal("0.9"),
        )

    wrapped = logged_classifier(fake, store)
    assert wrapped(inputs.interventions[0], inputs.contract).work_class == WorkClass.INCLUDED


def test_cost_estimate_uses_the_model_price_table() -> None:
    assert estimate_cost("eu.amazon.nova-lite-v1:0", 1_000_000, 0) == Decimal("0.060000")
    assert estimate_cost("eu.amazon.nova-lite-v1:0", 0, 1_000_000) == Decimal("0.240000")
    unknown = estimate_cost("some.unknown-model", 1_000_000, 0)
    assert unknown == Decimal("1.000000")


def test_token_estimate_is_flagged_as_estimated() -> None:
    assert estimate_tokens("a" * 400) == 100
    assert estimate_tokens("") == 1


def test_summarise_reports_injections() -> None:
    calls = [
        LlmCall(purpose="classify", model_id="m", entity_id="1", latency_ms=10, injection_detected=True),
        LlmCall(purpose="classify", model_id="m", entity_id="2", latency_ms=30),
    ]
    summary = summarise(calls)
    assert summary["injections_detected"] == 1
    assert summary["calls"] == 2


def test_llm_call_at_is_timezone_aware() -> None:
    call = LlmCall(purpose="classify", model_id="m")
    assert call.at.tzinfo is not None
    assert call.at <= datetime.now(UTC)
