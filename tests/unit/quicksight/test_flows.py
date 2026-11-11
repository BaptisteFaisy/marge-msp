"""The scheduled monthly review flow (EF-REV-01..03)."""

from __future__ import annotations

import pytest

from marge.quicksight import DASHBOARD_IDS, FLOW_IDS, FLOWS, flow_by_id


def test_one_monthly_review_flow_is_declared() -> None:
    assert len(FLOWS) == 1
    assert FLOW_IDS == ("FLOW-MONTHLY-REVIEW",)


def test_flow_covers_the_two_mandatory_requirements() -> None:
    flow = flow_by_id("FLOW-MONTHLY-REVIEW")
    assert "EF-REV-01" in flow.requirement
    assert "EF-REV-02" in flow.requirement


def test_flow_is_owned_by_the_controller() -> None:
    """A scheduled flow belongs to the user who creates it (spec 14.4)."""
    assert flow_by_id("FLOW-MONTHLY-REVIEW").owner == "controller"


def test_flow_runs_on_the_third_working_day() -> None:
    schedule = flow_by_id("FLOW-MONTHLY-REVIEW").schedule.lower()
    assert "third working day" in schedule
    assert "monthly" in schedule


def test_flow_reads_the_dashboards_and_the_topic() -> None:
    flow = flow_by_id("FLOW-MONTHLY-REVIEW")
    sources = " ".join(flow.sources)
    assert "marge_topic" in sources
    for dashboard in ("EF-TDB-01", "EF-TDB-03", "EF-TDB-04"):
        assert dashboard in flow.sources
    for source in flow.sources:
        if source.startswith("EF-TDB"):
            assert source in DASHBOARD_IDS


def test_flow_sends_to_the_direction_and_files_in_the_project_space() -> None:
    destinations = " ".join(flow_by_id("FLOW-MONTHLY-REVIEW").destinations)
    assert "email" in destinations.lower()
    assert "direction" in destinations.lower()
    assert "space" in destinations.lower()


def test_flow_has_ordered_steps() -> None:
    steps = flow_by_id("FLOW-MONTHLY-REVIEW").steps
    assert len(steps) >= 5
    orders = [step.order for step in steps]
    assert orders == sorted(orders)
    for step in steps:
        assert step.action
        assert step.detail


def test_flow_steps_end_with_sending_and_filing() -> None:
    actions = [step.action for step in flow_by_id("FLOW-MONTHLY-REVIEW").steps]
    assert "send" in actions
    assert "file" in actions


def test_flow_has_a_fallback() -> None:
    """EF-REV-03: a function builds the review when the flow does not suit."""
    fallback = flow_by_id("FLOW-MONTHLY-REVIEW").fallback
    assert "EF-REV-03" in fallback
    assert "ses" in fallback.lower()


def test_flow_uses_the_annex_e_template() -> None:
    flow = flow_by_id("FLOW-MONTHLY-REVIEW")
    assert "Annex E" in flow.template


def test_flow_unknown_id_raises() -> None:
    with pytest.raises(KeyError):
        flow_by_id("FLOW-NOPE")
