"""The five analytical datasets loaded into Quick (Annex A).

Each :class:`~marge.quicksight.models.DatasetSpec` carries the grain, the
columns, the key, and the Athena query that fills it. The SQL lives in
:mod:`marge.store.athena` so there is a single source of truth.
"""

from __future__ import annotations

from marge.store.athena import dataset_query

from .models import DatasetSpec, FieldSpec

__all__ = ["DATASETS", "DATASET_NAMES", "dataset_by_name"]

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
        sql=dataset_query("marge_client_mois"),
        description="Monthly margin of each client: revenue by post, cost by nature, margin, rate, coverage.",
        requirement="EF-TDB-01, EF-CAL-01, EF-ADM-02",
    ),
    DatasetSpec(
        name="effort_client_mois_categorie",
        grain="one client, one month, one work category, one level",
        fields=_EFFORT_FIELDS,
        keys=("client_id", "month", "category", "level"),
        sql=dataset_query("effort_client_mois_categorie"),
        description="Effort and labour cost split by category and by level, with the class of the work.",
        requirement="EF-TDB-05, EF-CAL-05",
    ),
    DatasetSpec(
        name="heures_non_facturees",
        grain="one client, one month",
        fields=_HEURES_NON_FACTUREES_FIELDS,
        keys=("client_id", "month"),
        sql=dataset_query("heures_non_facturees"),
        description="Unbilled hours per client and month, with their value and their state.",
        requirement="EF-TDB-03, EF-CAL-02",
    ),
    DatasetSpec(
        name="contrats_actifs",
        grain="one contract",
        fields=_CONTRATS_ACTIFS_FIELDS,
        keys=("contract_id", "version"),
        sql=dataset_query("contrats_actifs"),
        description="Contracts renewing within 90 days, with the six-month margin rate and the trend.",
        requirement="EF-TDB-04, EF-CTR-05",
    ),
    DatasetSpec(
        name="interventions_a_valider",
        grain="one intervention",
        fields=_INTERVENTIONS_A_VALIDER_FIELDS,
        keys=("intervention_id",),
        sql=dataset_query("interventions_a_valider"),
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
