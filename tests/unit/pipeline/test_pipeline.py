"""Tests for the pipeline orchestration package (nightly, weekly, monthly)."""

from __future__ import annotations

from decimal import Decimal

from tests.fakes.builders import (
    golden_aws_costs,
    golden_client,
    golden_contract,
    golden_interventions,
    golden_rates,
    golden_settings,
    golden_tooling,
)
from tests.fakes.fake_store import FakeStore

from marge.domain import Classification, Contract, DecisionStatus, Intervention, Month, Settings, WorkClass
from marge.pipeline import (
    assemble_inputs,
    build_queues,
    classify_pending,
    recalculate_month,
    run_monthly,
    run_nightly,
    run_weekly,
)


def _populated_store() -> tuple[FakeStore, Month]:
    store = FakeStore()
    month = Month.parse("2026-10")
    store.upsert_clients([golden_client()])
    store.save_contract(golden_contract())
    store.save_rates(golden_rates())
    store.save_tooling_costs(golden_tooling())
    store.save_aws_costs(golden_aws_costs())
    store.save_interventions(golden_interventions())
    return (store, month)


def test_assemble_inputs_gathers_all_dimensions() -> None:
    store, month = _populated_store()
    client = golden_client()
    inputs = assemble_inputs(store, client, month)
    assert inputs.client.client_id == client.client_id
    assert inputs.contract is not None
    assert len(inputs.interventions) == 6
    assert len(inputs.rates) == 3
    assert inputs.total_msp_hours == Decimal("55.00")


def test_classify_pending_classifies_and_queues() -> None:
    store, month = _populated_store()

    def fake_classifier(iv: Intervention, ct: Contract) -> Classification:
        out = "SQL" in iv.category
        return Classification(
            intervention_id=iv.intervention_id,
            client_id=ct.client_id,
            contract_version=ct.version,
            work_class=WorkClass.OUT_OF_SCOPE if out else WorkClass.INCLUDED,
            confidence=Decimal("0.90"),
            cited_clause="Article 3.2",
            billable_hours=iv.hours_spent,
            needs_human_validation=out,
            status=DecisionStatus.PENDING,
        )

    classified, reused, queued = classify_pending(store, golden_settings(), month, fake_classifier)
    assert classified == 6
    assert reused == 0
    assert queued == 1
    assert len(store.list_classifications()) == 6


def test_recalculate_month_persists_five_tables() -> None:
    store, month = _populated_store()
    clients, written, coverage = recalculate_month(store, golden_settings(), month)
    assert clients == 1
    assert written == 1
    assert coverage == Decimal("100.00")
    assert len(store.list_margin_months()) == 1
    assert len(store.list_hours_summaries()) == 1
    assert len(store.list_effort_slices()) > 0
    assert len(store.margin_lines("c-001", month)) > 0


def test_run_nightly_end_to_end() -> None:
    store, month = _populated_store()
    report = run_nightly(store, golden_settings(), month=month)
    assert report.month == month
    assert report.clients_recalculated == 1
    assert report.margins_written == 1
    assert report.coverage_percent == Decimal("100.00")
    assert report.duration_seconds >= Decimal("0")


def test_weekly_queues_group_by_account_manager() -> None:
    store, month = _populated_store()
    cls = Classification(
        intervention_id="wl-005",
        client_id="c-001",
        contract_version=1,
        work_class=WorkClass.OUT_OF_SCOPE,
        confidence=Decimal("0.88"),
        cited_clause="Article 3.2",
        billable_hours=Decimal("9"),
        needs_human_validation=True,
        status=DecisionStatus.PENDING,
    )
    store.save_classification(cls)
    queues = build_queues(store, month)
    assert len(queues) == 1
    assert queues[0].account_manager_id == "am-01"
    assert queues[0].hours == Decimal("9.00")
    assert queues[0].value == Decimal("990.00")

    report = run_weekly(store, golden_settings(), month=month)
    assert report.pending_total == 1
    assert report.hours_total == Decimal("9.00")
    assert report.value_total == Decimal("990.00")


def test_monthly_review_produces_text_and_figures() -> None:
    store, month = _populated_store()
    recalculate_month(store, golden_settings(), month)

    def dummy_builder(s: FakeStore, m: Month, cfg: Settings) -> object:
        class Agg:
            total_margin = Decimal("895.00")
            total_margin_rate = Decimal("0.1937")
            coverage_percent = Decimal("100.00")
            unbilled_hours = Decimal("9.00")
            unbilled_value = Decimal("990.00")
            clients_below_threshold = 0
            renewals_within_horizon = 0

        return Agg()

    def dummy_renderer(agg: object, cfg: Settings) -> str:
        return "# Revue 2026-10\nMarge: 895 EUR"

    rep = run_monthly(
        store,
        golden_settings(),
        month,
        recipients=("dir@msp.test",),
        aggregator=dummy_builder,
        renderer=dummy_renderer,
    )
    assert "895" in rep.review_text
    assert rep.figures["total_margin"] == "895.00"
    assert rep.recipients == ("dir@msp.test",)
