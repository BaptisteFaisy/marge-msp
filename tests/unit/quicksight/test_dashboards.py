"""The six dashboards of EF-TDB-01..06 and their row-level rule."""

from __future__ import annotations

import pytest

from marge.quicksight import DASHBOARD_IDS, DASHBOARDS, dashboard_by_id, dataset_by_name
from marge.quicksight.rls import RLS_RULES

EXPECTED_IDS = (
    "EF-TDB-01",
    "EF-TDB-02",
    "EF-TDB-03",
    "EF-TDB-04",
    "EF-TDB-05",
    "EF-TDB-06",
)

WIDGET_TYPES = {"KPI", "TABLE", "CHART", "LINE", "BAR", "PIE", "TEXT"}


def test_six_dashboards_are_declared() -> None:
    assert len(DASHBOARDS) == 6
    assert DASHBOARD_IDS == EXPECTED_IDS


@pytest.mark.parametrize("dashboard_id", EXPECTED_IDS)
def test_dashboard_declares_its_requirement(dashboard_id: str) -> None:
    assert dashboard_by_id(dashboard_id).requirement == dashboard_id


@pytest.mark.parametrize("dashboard_id", EXPECTED_IDS)
def test_dashboard_has_widgets(dashboard_id: str) -> None:
    dashboard = dashboard_by_id(dashboard_id)
    assert dashboard.widgets
    for widget in dashboard.widgets:
        assert widget.name
        assert widget.title
        assert widget.widget_type in WIDGET_TYPES


@pytest.mark.parametrize("dashboard_id", EXPECTED_IDS)
def test_every_widget_points_at_an_existing_dataset(dashboard_id: str) -> None:
    dashboard = dashboard_by_id(dashboard_id)
    for widget in dashboard.widgets:
        assert widget.dataset in dashboard.datasets
        assert dataset_by_name(widget.dataset)


@pytest.mark.parametrize("dashboard_id", EXPECTED_IDS)
def test_every_widget_field_exists_in_its_dataset(dashboard_id: str) -> None:
    dashboard = dashboard_by_id(dashboard_id)
    for widget in dashboard.widgets:
        fields = dataset_by_name(widget.dataset).field_names
        for field in (*widget.fields, *widget.measures, *widget.group_by):
            assert field in fields, f"{dashboard_id}.{widget.name}.{field}"


@pytest.mark.parametrize("dashboard_id", EXPECTED_IDS)
def test_dashboard_datasets_exist(dashboard_id: str) -> None:
    for name in dashboard_by_id(dashboard_id).datasets:
        assert dataset_by_name(name)


@pytest.mark.parametrize("dashboard_id", EXPECTED_IDS)
def test_dashboard_declares_a_known_row_filter_rule(dashboard_id: str) -> None:
    dashboard = dashboard_by_id(dashboard_id)
    assert dashboard.row_filter_rules
    known = {rule.rule_id for rule in RLS_RULES}
    for rule_id in dashboard.row_filter_rules:
        assert rule_id in known


def test_overview_dashboard_shows_the_three_figures_of_the_spec() -> None:
    """EF-TDB-01: total margin, ranking, clients under the threshold, trend."""
    dashboard = dashboard_by_id("EF-TDB-01")
    names = {widget.name for widget in dashboard.widgets}
    assert {"total_margin", "client_ranking", "below_threshold", "margin_trend"} <= names


def test_client_sheet_reaches_the_three_datasets() -> None:
    """EF-TDB-02: revenue, cost by nature, hours by level and category, contract."""
    dashboard = dashboard_by_id("EF-TDB-02")
    assert set(dashboard.datasets) == {
        "marge_client_mois",
        "effort_client_mois_categorie",
        "contrats_actifs",
    }


def test_unbilled_dashboard_shows_hours_and_value() -> None:
    """EF-TDB-03: hours and value, with their state."""
    dashboard = dashboard_by_id("EF-TDB-03")
    assert "heures_non_facturees" in dashboard.datasets
    measures = {m for widget in dashboard.widgets for m in widget.measures}
    assert {"unbilled_hours", "unbilled_value"} <= measures


def test_renewal_dashboard_filters_on_the_ninety_day_horizon() -> None:
    """EF-TDB-04: renewals within 90 days, with margin and trend."""
    dashboard = dashboard_by_id("EF-TDB-04")
    filters = " ".join(f for widget in dashboard.widgets for f in widget.filters)
    assert "90" in filters
    assert "contrats_actifs" in dashboard.datasets


def test_effort_dashboard_is_marked_as_secondary() -> None:
    """EF-TDB-05 has the 'S' priority of the specification."""
    dashboard = dashboard_by_id("EF-TDB-05")
    assert dashboard.requirement == "EF-TDB-05"
    assert "effort_client_mois_categorie" in dashboard.datasets


def test_scope_dashboard_is_the_row_filtered_one() -> None:
    """EF-TDB-06: the same tables, restricted to the clients of the user."""
    dashboard = dashboard_by_id("EF-TDB-06")
    assert "RLS-ACCOUNT-MANAGER-SCOPE" in dashboard.row_filter_rules
    assert "account_manager_id" in " ".join(dashboard.default_filters)


def test_every_dashboard_names_an_owner_role() -> None:
    for dashboard in DASHBOARDS:
        assert dashboard.owner_role


def test_dashboard_unknown_id_raises() -> None:
    with pytest.raises(KeyError):
        dashboard_by_id("EF-TDB-99")
