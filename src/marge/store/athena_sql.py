"""Athena SELECT queries for the five analytical datasets (spec 12, Annex A).

Kept apart from the DDL so both modules stay readable and under the size
limits; the identifiers they accept are validated by ``marge.store.athena_ident``.
"""

from __future__ import annotations

from .athena_ident import (
    validate_client_id,
    validate_identifier,
    validate_month,
)

_MARGES_CLIENT_MOIS_SQL = """
WITH marge AS (
    SELECT
        client_id,
        month,
        revenue_subscription,
        revenue_aws_resale,
        revenue_extra_hours_billed,
        revenue_projects,
        cost_labour,
        cost_tooling,
        cost_msp_aws,
        cost_penalties,
        margin,
        margin_rate,
        coverage,
        is_estimate,
        state,
        calc_version
    FROM {db}.marge_mensuelle
)
SELECT
    m.client_id,
    c.client_name,
    c.account_manager_id,
    m.month,
    m.revenue_subscription,
    m.revenue_aws_resale,
    m.revenue_extra_hours_billed,
    m.revenue_projects,
    m.revenue_subscription + m.revenue_aws_resale
        + m.revenue_extra_hours_billed + m.revenue_projects AS revenue_total,
    m.cost_labour,
    m.cost_tooling,
    m.cost_msp_aws,
    m.cost_penalties,
    m.cost_labour + m.cost_tooling + m.cost_msp_aws + m.cost_penalties AS cost_total,
    m.margin,
    m.margin_rate,
    m.coverage,
    m.is_estimate,
    m.state,
    m.calc_version
FROM marge m
JOIN {db}.clients c ON c.client_id = m.client_id
""".strip()

_EFFORT_SQL = """
WITH classed AS (
    SELECT
        i.client_id,
        i.occurred_on,
        i.category,
        i.level,
        i.ticket_id,
        i.hours_spent,
        COALESCE(cl.work_class, 'IN_SCOPE') AS work_class
    FROM {db}.interventions i
    LEFT JOIN {db}.classements cl ON cl.intervention_id = i.intervention_id
),
rated AS (
    SELECT
        k.*,
        r.hourly_cost,
        k.hours_spent * r.hourly_cost AS labour_cost
    FROM classed k
    JOIN {db}.couts_horaires r
      ON r.level = k.level
     AND r.effective_from <= LAST_DAY(CAST(k.occurred_on AS DATE))
     AND r.effective_from = (
            SELECT MAX(r2.effective_from)
            FROM {db}.couts_horaires r2
            WHERE r2.level = k.level
              AND r2.effective_from <= LAST_DAY(CAST(k.occurred_on AS DATE))
        )
)
SELECT
    rated.client_id,
    clients.account_manager_id,
    DATE_FORMAT(CAST(rated.occurred_on AS DATE), 'yyyy-MM') AS month,
    rated.category,
    rated.level,
    SUM(rated.hours_spent) AS hours_spent,
    SUM(rated.labour_cost) AS labour_cost,
    COUNT(DISTINCT rated.ticket_id) AS ticket_count,
    ANY_VALUE(rated.work_class) AS work_class,
    ANY_VALUE(rated.hourly_cost) AS hourly_cost
FROM rated
JOIN {db}.clients clients ON clients.client_id = rated.client_id
GROUP BY
    rated.client_id,
    clients.account_manager_id,
    DATE_FORMAT(CAST(rated.occurred_on AS DATE), 'yyyy-MM'),
    rated.category,
    rated.level
""".strip()

_HEURES_NON_FACTUREES_SQL = """
SELECT
    h.client_id,
    c.account_manager_id,
    h.month,
    h.out_of_scope_validated_hours,
    h.over_quota_hours,
    h.billed_extra_hours,
    h.out_of_scope_validated_hours + h.over_quota_hours - h.billed_extra_hours AS unbilled_hours,
    h.contract_hour_rate,
    (h.out_of_scope_validated_hours + h.over_quota_hours - h.billed_extra_hours)
        * h.contract_hour_rate AS unbilled_value,
    h.state
FROM {db}.heures_non_facturees h
JOIN {db}.clients c ON c.client_id = h.client_id
""".strip()

_CONTRATS_ACTIFS_SQL = """
WITH marge_6m AS (
    SELECT
        client_id,
        SUM(revenue_subscription + revenue_aws_resale
            + revenue_extra_hours_billed + revenue_projects) AS revenue_6m,
        SUM(cost_labour + cost_tooling + cost_msp_aws + cost_penalties) AS cost_6m
    FROM {db}.marge_mensuelle
    WHERE month >= date_format(current_date, 'yyyy-MM')
              - INTERVAL '5' MONTH
    GROUP BY client_id
),
trend AS (
    SELECT
        client_id,
        CASE
            WHEN margin_rate - LAG(margin_rate) OVER (
                     PARTITION BY client_id ORDER BY month) >  0.005 THEN 'UP'
            WHEN margin_rate - LAG(margin_rate) OVER (
                     PARTITION BY client_id ORDER BY month) < -0.005 THEN 'DOWN'
            ELSE 'FLAT'
        END AS trend
    FROM {db}.marge_mensuelle
)
SELECT
    ct.contract_id,
    ct.version,
    ct.client_id,
    c.client_name,
    c.account_manager_id,
    ct.monthly_subscription,
    ct.included_hours_per_month,
    ct.extra_hour_rate,
    ct.end_date,
    DATE_DIFF('day', current_date, ct.end_date) AS days_to_renewal,
    CASE WHEN m.revenue_6m > 0
         THEN (m.revenue_6m - m.cost_6m) / m.revenue_6m
         ELSE 0 END AS margin_rate_six_months,
    COALESCE(t.trend, 'FLAT') AS trend,
    ct.status
FROM {db}.contrats ct
JOIN {db}.clients c ON c.client_id = ct.client_id
LEFT JOIN marge_6m m ON m.client_id = ct.client_id
LEFT JOIN trend t ON t.client_id = ct.client_id
WHERE ct.status IN ('VALIDATED', 'AMENDED')
  AND ct.end_date IS NOT NULL
  AND DATE_DIFF('day', current_date, ct.end_date) BETWEEN 0 AND 90
""".strip()

_INTERVENTIONS_A_VALIDER_SQL = """
SELECT
    i.intervention_id,
    i.ticket_id,
    i.client_id,
    c.client_name,
    c.account_manager_id,
    i.occurred_on,
    i.category,
    i.level,
    i.hours_spent,
    cl.work_class AS proposed_class,
    cl.confidence,
    cl.cited_clause,
    cl.reason,
    cl.needs_human_validation,
    cl.status AS decision_status
FROM {db}.classements cl
JOIN {db}.interventions i ON i.intervention_id = cl.intervention_id
JOIN {db}.clients c ON c.client_id = i.client_id
WHERE cl.status = 'PENDING'
  AND cl.work_class IN ('OUT_OF_SCOPE', 'UNCERTAIN')
""".strip()

_MARGIN_RECALC_SQL = """
WITH revenue AS (
    SELECT ct.client_id, '{month}' AS month,
        COALESCE(ct.monthly_subscription, 0) AS revenue_subscription,
        COALESCE(SUM(a.rebilled_amount - a.cost), 0) AS revenue_aws_resale,
        COALESCE(SUM(CASE WHEN inv.kind = 'EXTRA_HOURS' THEN inv.amount ELSE 0 END), 0)
            AS revenue_extra_hours_billed,
        COALESCE(SUM(CASE WHEN inv.kind = 'PROJECT' THEN inv.amount ELSE 0 END), 0)
            AS revenue_projects
    FROM {db}.contrats ct
    LEFT JOIN {db}.couts_aws a
           ON a.client_id = ct.client_id AND a.month = '{month}' AND a.kind = 'CLIENT_ACCOUNT'
    LEFT JOIN {db}.factures inv ON inv.client_id = ct.client_id AND inv.month = '{month}'
    WHERE ct.status = 'VALIDATED'
    GROUP BY ct.client_id, ct.monthly_subscription
),
labour AS (
    SELECT i.client_id,
        SUM(i.hours_spent * r.hourly_cost) AS cost_labour,
        SUM(CASE WHEN i.client_id IS NOT NULL AND i.client_id <> 'UNASSIGNED'
                 THEN i.hours_spent ELSE 0 END) AS attributed_hours,
        SUM(i.hours_spent) AS total_hours,
        SUM(CASE WHEN cl.work_class = 'OUT_OF_SCOPE' AND cl.status = 'APPROVED'
                 THEN i.hours_spent ELSE 0 END) AS oos_validated_hours
    FROM {db}.interventions i
    LEFT JOIN {db}.classements cl ON cl.intervention_id = i.intervention_id
    JOIN {db}.couts_horaires r ON r.level = i.level AND r.effective_from = (
        SELECT MAX(r2.effective_from) FROM {db}.couts_horaires r2
        WHERE r2.level = i.level AND r2.effective_from <= LAST_DAY(DATE '{month}-01'))
    WHERE DATE_FORMAT(CAST(i.occurred_on AS DATE), 'yyyy-MM') = '{month}'
    GROUP BY i.client_id
),
other_costs AS (
    SELECT c.client_id,
        COALESCE(SUM(t.monthly_cost), 0) AS cost_tooling,
        COALESCE(SUM(a.cost), 0) AS cost_msp_aws,
        COALESCE(SUM(p.amount), 0) AS cost_penalties
    FROM {db}.clients c
    LEFT JOIN {db}.outillage t ON t.client_id = c.client_id
    LEFT JOIN {db}.couts_aws a ON a.client_id = c.client_id
        AND a.month = '{month}' AND a.kind = 'MSP_TOOLING_ACCOUNT'
    LEFT JOIN {db}.penalites p ON p.client_id = c.client_id AND p.month = '{month}'
    GROUP BY c.client_id
),
totals AS (
    SELECT rev.client_id, rev.month,
        rev.revenue_subscription, rev.revenue_aws_resale,
        rev.revenue_extra_hours_billed, rev.revenue_projects,
        (rev.revenue_subscription + rev.revenue_aws_resale
            + rev.revenue_extra_hours_billed + rev.revenue_projects) AS revenue_total,
        COALESCE(lab.cost_labour, 0) AS cost_labour,
        oc.cost_tooling, oc.cost_msp_aws, oc.cost_penalties,
        (COALESCE(lab.cost_labour, 0) + oc.cost_tooling
            + oc.cost_msp_aws + oc.cost_penalties) AS cost_total,
        COALESCE(lab.oos_validated_hours, 0) AS out_of_scope_validated_hours,
        CASE WHEN COALESCE(lab.total_hours, 0) > 0
             THEN lab.attributed_hours / lab.total_hours ELSE 1 END AS coverage
    FROM revenue rev
    LEFT JOIN labour lab ON lab.client_id = rev.client_id
    JOIN other_costs oc ON oc.client_id = rev.client_id
)
SELECT client_id, month,
    revenue_subscription, revenue_aws_resale, revenue_extra_hours_billed, revenue_projects,
    revenue_total, cost_labour, cost_tooling, cost_msp_aws, cost_penalties, cost_total,
    revenue_total - cost_total AS margin,
    CASE WHEN revenue_total > 0
         THEN (revenue_total - cost_total) / revenue_total ELSE 0 END AS margin_rate,
    out_of_scope_validated_hours, coverage
FROM totals
""".strip()

_QUERY_TEMPLATES: dict[str, str] = {
    "marge_client_mois": _MARGES_CLIENT_MOIS_SQL,
    "effort_client_mois_categorie": _EFFORT_SQL,
    "heures_non_facturees": _HEURES_NON_FACTUREES_SQL,
    "contrats_actifs": _CONTRATS_ACTIFS_SQL,
    "interventions_a_valider": _INTERVENTIONS_A_VALIDER_SQL,
}


def dataset_query(name: str, *, database: str = "marge") -> str:
    """Return the Athena ``SELECT`` query for one Annex A dataset."""
    db = validate_identifier(database, "database")
    return _QUERY_TEMPLATES[name].format(db=db)


def margin_recalculation_query(month: str, *, database: str = "marge", client_id: str | None = None) -> str:
    """Return the Chapter 12 margin recalculation SQL for a given ``YYYY-MM``."""
    db = validate_identifier(database, "database")
    validate_month(month)
    sql = _MARGIN_RECALC_SQL.format(db=db, month=month)
    if client_id is not None:
        sql = f"{sql}\nWHERE client_id = '{validate_client_id(client_id)}'"
    return sql


__all__ = ["dataset_query", "margin_recalculation_query"]
