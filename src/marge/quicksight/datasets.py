"""The five analytical datasets loaded into Quick (Annex A).

Each :class:`~marge.quicksight.models.DatasetSpec` carries the grain, the
columns, the key, and the Athena query that fills it. The queries read the
model-common tables described in spec 15, produced by the nightly pipeline.

The SQL lives here because ``marge.store.athena`` does not exist yet; when it
lands, the queries below must be replaced by its, keeping the same contract:
one dataset, one grain, one query.
"""

from __future__ import annotations

from .models import DatasetSpec, FieldSpec

__all__ = ["DATASETS", "DATASET_NAMES", "dataset_by_name"]

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
    FROM marge.marge_mensuelle
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
JOIN marge.clients c ON c.client_id = m.client_id
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
    FROM marge.interventions i
    LEFT JOIN marge.classements cl ON cl.intervention_id = i.intervention_id
),
rated AS (
    SELECT
        k.*,
        r.hourly_cost,
        k.hours_spent * r.hourly_cost AS labour_cost
    FROM classed k
    JOIN marge.couts_horaires r
      ON r.level = k.level
     AND r.effective_from <= LAST_DAY(CAST(k.occurred_on AS DATE))
     AND r.effective_from = (
            SELECT MAX(r2.effective_from)
            FROM marge.couts_horaires r2
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
JOIN marge.clients clients ON clients.client_id = rated.client_id
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
FROM marge.heures_non_facturees h
JOIN marge.clients c ON c.client_id = h.client_id
""".strip()

_CONTRATS_ACTIFS_SQL = """
WITH marge_6m AS (
    SELECT
        client_id,
        SUM(revenue_subscription + revenue_aws_resale
            + revenue_extra_hours_billed + revenue_projects) AS revenue_6m,
        SUM(cost_labour + cost_tooling + cost_msp_aws + cost_penalties) AS cost_6m
    FROM marge.marge_mensuelle
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
    FROM marge.marge_mensuelle
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
FROM marge.contrats ct
JOIN marge.clients c ON c.client_id = ct.client_id
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
FROM marge.classements cl
JOIN marge.interventions i ON i.intervention_id = cl.intervention_id
JOIN marge.clients c ON c.client_id = i.client_id
WHERE cl.status = 'PENDING'
  AND cl.work_class IN ('OUT_OF_SCOPE', 'UNCERTAIN')
""".strip()


_MARGES_FIELDS = (
    FieldSpec("client_id", "string", "Common client identifier", sensitive=False),
    FieldSpec("client_name", "string", "Client commercial name"),
    FieldSpec("account_manager_id", "string", "Owner of the client relationship"),
    FieldSpec("month", "string", "Month of the calculation, YYYY-MM"),
    FieldSpec("revenue_subscription", "decimal", "Managed services subscription", unit="EUR"),
    FieldSpec("revenue_aws_resale", "decimal", "AWS resale margin", unit="EUR"),
    FieldSpec("revenue_extra_hours_billed", "decimal", "Billed extra hours", unit="EUR"),
    FieldSpec("revenue_projects", "decimal", "Billed projects", unit="EUR"),
    FieldSpec("revenue_total", "decimal", "Total revenue", unit="EUR"),
    FieldSpec("cost_labour", "decimal", "Labour cost", unit="EUR"),
    FieldSpec("cost_tooling", "decimal", "Allocated tooling cost", unit="EUR"),
    FieldSpec("cost_msp_aws", "decimal", "AWS cost carried by the MSP", unit="EUR"),
    FieldSpec("cost_penalties", "decimal", "SLA penalties paid", unit="EUR"),
    FieldSpec("cost_total", "decimal", "Total cost", unit="EUR"),
    FieldSpec("margin", "decimal", "Revenue minus cost", unit="EUR"),
    FieldSpec("margin_rate", "decimal", "Margin divided by revenue", unit="ratio"),
    FieldSpec("coverage", "decimal", "Share of hours attached to a client", unit="ratio"),
    FieldSpec("is_estimate", "boolean", "True when the month is an estimate"),
    FieldSpec("state", "string", "COMPLETE, ESTIMATE or INCOMPLETE"),
    FieldSpec("calc_version", "integer", "Version of the calculation model"),
)

_EFFORT_FIELDS = (
    FieldSpec("client_id", "string", "Common client identifier"),
    FieldSpec("account_manager_id", "string", "Owner of the client relationship"),
    FieldSpec("month", "string", "Month of the slice, YYYY-MM"),
    FieldSpec("category", "string", "Work category"),
    FieldSpec("level", "string", "Skill level, never a person (ENF-CONF-01)"),
    FieldSpec("hours_spent", "decimal", "Hours spent", unit="hours"),
    FieldSpec("labour_cost", "decimal", "Labour cost of the slice", unit="EUR"),
    FieldSpec("ticket_count", "integer", "Distinct tickets behind the slice"),
    FieldSpec("work_class", "string", "IN_SCOPE, OUT_OF_SCOPE or UNCERTAIN"),
    FieldSpec("hourly_cost", "decimal", "Hourly cost of the level in force", unit="EUR", sensitive=True),
)

_HEURES_NON_FACTUREES_FIELDS = (
    FieldSpec("client_id", "string", "Common client identifier"),
    FieldSpec("account_manager_id", "string", "Owner of the client relationship"),
    FieldSpec("month", "string", "Month of the summary, YYYY-MM"),
    FieldSpec("out_of_scope_validated_hours", "decimal", "Validated out-of-scope hours", unit="hours"),
    FieldSpec("over_quota_hours", "decimal", "Hours above the contract quota", unit="hours"),
    FieldSpec("billed_extra_hours", "decimal", "Extra hours already invoiced", unit="hours"),
    FieldSpec("unbilled_hours", "decimal", "Unbilled hours after validation", unit="hours"),
    FieldSpec("contract_hour_rate", "decimal", "Contractual hourly rate", unit="EUR", sensitive=True),
    FieldSpec("unbilled_value", "decimal", "Unbilled hours times the contract rate", unit="EUR"),
    FieldSpec("state", "string", "DETECTED, VALIDATED, BILLED or WRITTEN_OFF"),
)

_CONTRATS_ACTIFS_FIELDS = (
    FieldSpec("contract_id", "string", "Contract identifier"),
    FieldSpec("version", "integer", "Contract version"),
    FieldSpec("client_id", "string", "Common client identifier"),
    FieldSpec("client_name", "string", "Client commercial name"),
    FieldSpec("account_manager_id", "string", "Owner of the client relationship"),
    FieldSpec("monthly_subscription", "decimal", "Monthly subscription", unit="EUR"),
    FieldSpec("included_hours_per_month", "decimal", "Hours included in the subscription", unit="hours"),
    FieldSpec("extra_hour_rate", "decimal", "Hourly rate beyond the quota", unit="EUR", sensitive=True),
    FieldSpec("end_date", "date", "Renewal date of the contract"),
    FieldSpec("days_to_renewal", "integer", "Days left before renewal"),
    FieldSpec("margin_rate_six_months", "decimal", "Margin rate over the last six months", unit="ratio"),
    FieldSpec("trend", "string", "UP, DOWN or FLAT"),
    FieldSpec("status", "string", "Contract validation status"),
)

_INTERVENTIONS_A_VALIDER_FIELDS = (
    FieldSpec("intervention_id", "string", "Intervention identifier"),
    FieldSpec("ticket_id", "string", "Ticket identifier in the ITSM tool"),
    FieldSpec("client_id", "string", "Common client identifier"),
    FieldSpec("client_name", "string", "Client commercial name"),
    FieldSpec("account_manager_id", "string", "Owner of the client relationship"),
    FieldSpec("occurred_on", "date", "Date of the intervention"),
    FieldSpec("category", "string", "Work category"),
    FieldSpec("level", "string", "Skill level, never a person (ENF-CONF-01)"),
    FieldSpec("hours_spent", "decimal", "Duration spent", unit="hours"),
    FieldSpec("proposed_class", "string", "Class proposed by the model"),
    FieldSpec("confidence", "decimal", "Confidence of the proposal", unit="ratio"),
    FieldSpec("cited_clause", "string", "Contract clause that delimits the scope"),
    FieldSpec("reason", "string", "Reason given for the proposal"),
    FieldSpec("needs_human_validation", "boolean", "True when a human must decide"),
    FieldSpec("decision_status", "string", "PENDING, APPROVED, CORRECTED or REJECTED"),
)

DATASETS: tuple[DatasetSpec, ...] = (
    DatasetSpec(
        name="marge_client_mois",
        grain="one client, one month",
        fields=_MARGES_FIELDS,
        keys=("client_id", "month"),
        sql=_MARGES_CLIENT_MOIS_SQL,
        description="Monthly margin of each client: revenue by post, cost by nature, margin, rate, coverage.",
        requirement="EF-TDB-01, EF-CAL-01, EF-ADM-02",
    ),
    DatasetSpec(
        name="effort_client_mois_categorie",
        grain="one client, one month, one work category, one level",
        fields=_EFFORT_FIELDS,
        keys=("client_id", "month", "category", "level"),
        sql=_EFFORT_SQL,
        description="Effort and labour cost split by category and by level, with the class of the work.",
        requirement="EF-TDB-05, EF-CAL-05",
    ),
    DatasetSpec(
        name="heures_non_facturees",
        grain="one client, one month",
        fields=_HEURES_NON_FACTUREES_FIELDS,
        keys=("client_id", "month"),
        sql=_HEURES_NON_FACTUREES_SQL,
        description="Unbilled hours per client and month, with their value and their state.",
        requirement="EF-TDB-03, EF-CAL-02",
    ),
    DatasetSpec(
        name="contrats_actifs",
        grain="one contract",
        fields=_CONTRATS_ACTIFS_FIELDS,
        keys=("contract_id", "version"),
        sql=_CONTRATS_ACTIFS_SQL,
        description="Contracts renewing within 90 days, with the six-month margin rate and the trend.",
        requirement="EF-TDB-04, EF-CTR-05",
    ),
    DatasetSpec(
        name="interventions_a_valider",
        grain="one intervention",
        fields=_INTERVENTIONS_A_VALIDER_FIELDS,
        keys=("intervention_id",),
        sql=_INTERVENTIONS_A_VALIDER_SQL,
        description="Classifications awaiting a human decision, with the cited contract clause.",
        requirement="EF-CLS-03, EF-TDB-03",
    ),
)

DATASET_NAMES: tuple[str, ...] = tuple(dataset.name for dataset in DATASETS)


def dataset_by_name(name: str) -> DatasetSpec:
    """Return the dataset named ``name`` or raise ``KeyError``."""
    for dataset in DATASETS:
        if dataset.name == name:
            return dataset
    raise KeyError(f"no dataset named {name!r}")
