"""The Quick Sight dashboards (EF-TDB-01..06).

Each dashboard lists its widgets: type, source dataset, fields, measures and
filters. Every widget points at one of the five datasets of Annex A and every
dashboard declares the row-level rules that apply to it (EF-TDB-06).
"""

from __future__ import annotations

from .models import DashboardSpec, WidgetSpec

__all__ = ["DASHBOARDS", "DASHBOARD_IDS", "dashboard_by_id"]


def _widget(
    name: str,
    widget_type: str,
    title: str,
    dataset: str,
    fields: tuple[str, ...],
    measures: tuple[str, ...] = (),
    filters: tuple[str, ...] = (),
    group_by: tuple[str, ...] = (),
    sort_by: str = "",
    description: str = "",
) -> WidgetSpec:
    """Build a widget of a dashboard."""
    return WidgetSpec(
        name=name,
        widget_type=widget_type,
        title=title,
        dataset=dataset,
        fields=fields,
        measures=measures,
        filters=filters,
        group_by=group_by,
        sort_by=sort_by,
        description=description,
    )


_OVERVIEW_WIDGETS = (
    _widget(
        "total_margin",
        "KPI",
        "Total margin of the period",
        "marge_client_mois",
        ("client_id", "month", "margin", "is_estimate"),
        measures=("margin",),
        description="Sum of the monthly margin of the selected clients and months.",
    ),
    _widget(
        "margin_rate",
        "KPI",
        "Margin rate",
        "marge_client_mois",
        ("client_id", "month", "margin", "revenue_total"),
        measures=("margin_rate",),
        description="Revenue-weighted margin rate, computed by the topic.",
    ),
    _widget(
        "client_ranking",
        "TABLE",
        "Clients ranked by margin",
        "marge_client_mois",
        ("client_id", "client_name", "margin", "margin_rate", "coverage", "is_estimate"),
        group_by=("client_id", "client_name"),
        sort_by="margin DESC",
        description="One row per client over the selected period.",
    ),
    _widget(
        "below_threshold",
        "TABLE",
        "Clients below the margin threshold",
        "marge_client_mois",
        ("client_id", "client_name", "margin_rate", "coverage"),
        filters=("margin_rate < threshold (20 % by default, EF-ADM-01)",),
        group_by=("client_id", "client_name"),
        sort_by="margin_rate ASC",
        description="Clients whose margin rate is under the configured threshold.",
    ),
    _widget(
        "margin_trend",
        "LINE",
        "Margin trend month over month",
        "marge_client_mois",
        ("client_id", "month", "margin", "margin_rate"),
        group_by=("month",),
        sort_by="month ASC",
        description="Monthly series of the margin of the selection.",
    ),
    _widget(
        "coverage",
        "KPI",
        "Data coverage",
        "marge_client_mois",
        ("client_id", "month", "coverage", "is_estimate"),
        measures=("coverage",),
        description="Trust indicator of every other figure of the dashboard (EF-ADM-02).",
    ),
)

_CLIENT_WIDGETS = (
    _widget(
        "client_revenue",
        "TABLE",
        "Revenue by post",
        "marge_client_mois",
        (
            "client_id",
            "month",
            "revenue_subscription",
            "revenue_aws_resale",
            "revenue_extra_hours_billed",
            "revenue_projects",
            "revenue_total",
        ),
        group_by=("month",),
        sort_by="month DESC",
        description="The four revenue posts of spec 12.1 for the selected client.",
    ),
    _widget(
        "client_costs",
        "TABLE",
        "Cost by nature",
        "marge_client_mois",
        ("client_id", "month", "cost_labour", "cost_tooling", "cost_msp_aws", "cost_penalties"),
        group_by=("month",),
        sort_by="month DESC",
        description="The four cost natures of spec 12.2 for the selected client.",
    ),
    _widget(
        "client_margin",
        "KPI",
        "Margin and margin rate",
        "marge_client_mois",
        ("client_id", "month", "margin", "margin_rate", "is_estimate"),
        measures=("margin", "margin_rate"),
        description="Margin of the selected client, flagged when it is an estimate.",
    ),
    _widget(
        "hours_by_level",
        "TABLE",
        "Hours by level",
        "effort_client_mois_categorie",
        ("client_id", "month", "level", "hours_spent", "labour_cost"),
        group_by=("level", "month"),
        description="Levels only, never a named person (ENF-CONF-02).",
    ),
    _widget(
        "hours_by_category",
        "BAR",
        "Hours by work category",
        "effort_client_mois_categorie",
        ("client_id", "month", "category", "hours_spent", "ticket_count", "work_class"),
        group_by=("category",),
        sort_by="hours_spent DESC",
        description="Where the hours of the client went, with the class of the work.",
    ),
    _widget(
        "quota",
        "KPI",
        "Quota consumption of the contract",
        "contrats_actifs",
        ("client_id", "included_hours_per_month", "extra_hour_rate"),
        measures=("included_hours_per_month",),
        description="Hours included in the subscription of the active contract.",
    ),
    _widget(
        "contract",
        "TEXT",
        "Contract of the client",
        "contrats_actifs",
        (
            "contract_id",
            "version",
            "monthly_subscription",
            "included_hours_per_month",
            "extra_hour_rate",
            "end_date",
            "days_to_renewal",
            "trend",
        ),
        description="Commercial terms of the active contract of the selected client.",
    ),
)

_UNBILLED_WIDGETS = (
    _widget(
        "unbilled_total",
        "KPI",
        "Unbilled hours and value",
        "heures_non_facturees",
        ("client_id", "month", "unbilled_hours", "unbilled_value"),
        measures=("unbilled_hours", "unbilled_value"),
        description="Hours not invoiced and what they represent at the contract rate.",
    ),
    _widget(
        "unbilled_by_client",
        "TABLE",
        "Unbilled hours by client",
        "heures_non_facturees",
        (
            "client_id",
            "month",
            "out_of_scope_validated_hours",
            "over_quota_hours",
            "billed_extra_hours",
            "unbilled_hours",
            "unbilled_value",
        ),
        group_by=("client_id", "month"),
        sort_by="unbilled_value DESC",
        description="Split between validated out-of-scope hours and hours above the quota.",
    ),
    _widget(
        "unbilled_by_state",
        "PIE",
        "Unbilled hours by state",
        "heures_non_facturees",
        ("client_id", "month", "unbilled_hours", "state"),
        group_by=("state",),
        measures=("unbilled_hours",),
        description="DETECTED, VALIDATED, BILLED or WRITTEN_OFF.",
    ),
    _widget(
        "pending_validation",
        "TABLE",
        "Classifications waiting for a human",
        "interventions_a_valider",
        (
            "intervention_id",
            "client_id",
            "occurred_on",
            "category",
            "hours_spent",
            "proposed_class",
            "cited_clause",
        ),
        filters=("decision_status = PENDING",),
        sort_by="occurred_on DESC",
        description="Every pending decision, with the clause that delimits the scope.",
    ),
)

_RENEWAL_WIDGETS = (
    _widget(
        "renewal_count",
        "KPI",
        "Contracts renewing within 90 days",
        "contrats_actifs",
        ("contract_id", "client_id", "days_to_renewal", "margin_rate_six_months", "trend"),
        measures=("days_to_renewal",),
        filters=("0 <= days_to_renewal <= 90",),
        description="Renewal watch window of EF-CTR-05.",
    ),
    _widget(
        "renewal_table",
        "TABLE",
        "Renewals with margin and trend",
        "contrats_actifs",
        (
            "contract_id",
            "client_id",
            "client_name",
            "end_date",
            "days_to_renewal",
            "monthly_subscription",
            "margin_rate_six_months",
            "trend",
        ),
        filters=("0 <= days_to_renewal <= 90",),
        sort_by="days_to_renewal ASC",
        description="Sorted by urgency; the trend column comes from the topic.",
    ),
    _widget(
        "renewal_falling",
        "TABLE",
        "Renewals whose margin is falling",
        "contrats_actifs",
        ("contract_id", "client_id", "end_date", "days_to_renewal", "margin_rate_six_months", "trend"),
        filters=("0 <= days_to_renewal <= 90", "trend = DOWN"),
        description="Contracts to renegotiate before the deadline.",
    ),
)

_EFFORT_WIDGETS = (
    _widget(
        "costliest_categories",
        "BAR",
        "Work categories that cost the most",
        "effort_client_mois_categorie",
        ("client_id", "month", "category", "labour_cost", "hours_spent", "ticket_count"),
        group_by=("category",),
        measures=("labour_cost",),
        sort_by="labour_cost DESC",
        description="Labour cost of each work category over the selected period.",
    ),
    _widget(
        "effort_by_client",
        "TABLE",
        "Effort by client",
        "effort_client_mois_categorie",
        ("client_id", "month", "category", "level", "hours_spent", "labour_cost", "ticket_count"),
        group_by=("client_id", "month"),
        sort_by="labour_cost DESC",
        description="Effort and labour cost of each client.",
    ),
    _widget(
        "cost_per_ticket",
        "TABLE",
        "Cost per ticket by category",
        "effort_client_mois_categorie",
        ("client_id", "month", "category", "labour_cost", "ticket_count", "work_class"),
        measures=("labour_cost", "ticket_count"),
        group_by=("category",),
        description="Labour cost divided by the number of tickets.",
    ),
)

_SCOPE_WIDGETS = (
    _widget(
        "my_clients",
        "TABLE",
        "Clients of the signed-in account manager",
        "marge_client_mois",
        ("client_id", "client_name", "account_manager_id", "month", "margin", "margin_rate"),
        group_by=("client_id", "client_name"),
        sort_by="margin_rate ASC",
        description="Row-level filter applied by the session parameter.",
    ),
    _widget(
        "my_unbilled",
        "KPI",
        "Unbilled hours of the portfolio",
        "heures_non_facturees",
        ("client_id", "month", "unbilled_hours", "unbilled_value", "state"),
        measures=("unbilled_hours", "unbilled_value"),
        description="Same row-level filter as the rest of the portfolio.",
    ),
    _widget(
        "my_renewals",
        "TABLE",
        "Renewals of the portfolio",
        "contrats_actifs",
        ("contract_id", "client_id", "end_date", "days_to_renewal", "margin_rate_six_months", "trend"),
        filters=("0 <= days_to_renewal <= 90",),
        sort_by="days_to_renewal ASC",
        description="Renewal watch restricted to the clients of the signed-in account manager.",
    ),
)

DASHBOARDS: tuple[DashboardSpec, ...] = (
    DashboardSpec(
        dashboard_id="EF-TDB-01",
        title="Profitability overview",
        requirement="EF-TDB-01",
        description=(
            "Total margin of the period, ranking of the clients, clients under the threshold "
            "and the month-over-month trend, with the coverage indicator."
        ),
        datasets=("marge_client_mois",),
        widgets=_OVERVIEW_WIDGETS,
        row_filter_rules=("RLS-ACCOUNT-MANAGER-SCOPE",),
        owner_role="EXECUTIVE",
        default_filters=("month is not null",),
    ),
    DashboardSpec(
        dashboard_id="EF-TDB-02",
        title="Client sheet",
        requirement="EF-TDB-02",
        description=(
            "Revenue, cost by nature, hours by level and by category, contract quota and "
            "commercial terms of one client."
        ),
        datasets=("marge_client_mois", "effort_client_mois_categorie", "contrats_actifs"),
        widgets=_CLIENT_WIDGETS,
        row_filter_rules=("RLS-ACCOUNT-MANAGER-SCOPE", "RLS-HOURLY-COST-RESTRICTED"),
        owner_role="ACCOUNT_MANAGER",
        default_filters=("client_id is selected",),
    ),
    DashboardSpec(
        dashboard_id="EF-TDB-03",
        title="Unbilled hours",
        requirement="EF-TDB-03",
        description=(
            "Unbilled hours by client, in hours and in value, with their state and the "
            "classifications waiting for a human."
        ),
        datasets=("heures_non_facturees", "interventions_a_valider"),
        widgets=_UNBILLED_WIDGETS,
        row_filter_rules=("RLS-ACCOUNT-MANAGER-SCOPE",),
        owner_role="ACCOUNT_MANAGER",
        default_filters=("month is not null",),
    ),
    DashboardSpec(
        dashboard_id="EF-TDB-04",
        title="Renewals within 90 days",
        requirement="EF-TDB-04",
        description="Contracts renewing within 90 days, with their margin rate and their trend.",
        datasets=("contrats_actifs",),
        widgets=_RENEWAL_WIDGETS,
        row_filter_rules=("RLS-ACCOUNT-MANAGER-SCOPE",),
        owner_role="ACCOUNT_MANAGER",
        default_filters=("0 <= days_to_renewal <= 90",),
    ),
    DashboardSpec(
        dashboard_id="EF-TDB-05",
        title="Effort",
        requirement="EF-TDB-05",
        description="Work types that cost the most, by client, by category and by level.",
        datasets=("effort_client_mois_categorie",),
        widgets=_EFFORT_WIDGETS,
        row_filter_rules=("RLS-ACCOUNT-MANAGER-SCOPE", "RLS-HOURLY-COST-RESTRICTED"),
        owner_role="OPERATIONS_DIRECTOR",
        default_filters=("month is not null",),
    ),
    DashboardSpec(
        dashboard_id="EF-TDB-06",
        title="My portfolio (row-level filtering)",
        requirement="EF-TDB-06",
        description=(
            "The same analytical tables, restricted by the row-level rule to the clients of "
            "the signed-in account manager."
        ),
        datasets=("marge_client_mois", "heures_non_facturees", "contrats_actifs"),
        widgets=_SCOPE_WIDGETS,
        row_filter_rules=("RLS-ACCOUNT-MANAGER-SCOPE", "RLS-HOURLY-COST-RESTRICTED"),
        owner_role="ACCOUNT_MANAGER",
        default_filters=("account_manager_id = session parameter",),
    ),
)

DASHBOARD_IDS: tuple[str, ...] = tuple(dashboard.dashboard_id for dashboard in DASHBOARDS)


def dashboard_by_id(dashboard_id: str) -> DashboardSpec:
    """Return the dashboard ``dashboard_id`` or raise ``KeyError``."""
    for dashboard in DASHBOARDS:
        if dashboard.dashboard_id == dashboard_id:
            return dashboard
    raise KeyError(f"no dashboard named {dashboard_id!r}")
