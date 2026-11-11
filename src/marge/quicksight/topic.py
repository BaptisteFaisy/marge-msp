"""The Quick Sight topic: the semantic layer of Marge (spec 14.1).

The topic carries the definitions of the margin, of the effort and of the
unbilled hours, the business synonyms, the default aggregations and the
joins between the five datasets. Every question about the margin goes through
it, so two people get the same number.

The definitions repeat the formulas of spec 12 as *text*. They never compute
anything: the figures come from ``marge.calc`` (ENF-IA-01).
"""

from __future__ import annotations

from .datasets import DATASET_NAMES
from .models import JoinSpec, MetricSpec, SynonymSpec, TopicSpec

__all__ = ["MARGIN_SYNONYMS", "TOPIC"]

MARGIN_SYNONYMS: tuple[str, ...] = (
    "rentabilite",
    "marge",
    "ce que le client rapporte",
    "profit",
    "margin",
)
"""Business words that all mean the margin metric (spec 14.1)."""


def _metric(
    name: str,
    label: str,
    definition: str,
    formula: str,
    unit: str,
    aggregation: str,
    dataset: str,
    fields: tuple[str, ...],
    synonyms: tuple[str, ...] = (),
) -> MetricSpec:
    """Build a metric of the topic."""
    return MetricSpec(
        name=name,
        label=label,
        definition=definition,
        formula=formula,
        unit=unit,
        default_aggregation=aggregation,
        source_dataset=dataset,
        source_fields=fields,
        synonyms=synonyms,
    )


_METRICS: tuple[MetricSpec, ...] = (
    _metric(
        name="margin",
        label="Margin",
        definition=(
            "What the client brings to the MSP over the period: revenue minus cost. "
            "Revenue is the subscription, the AWS resale margin, the billed extra hours and the "
            "billed projects. Cost is the labour, the allocated tooling, the AWS carried by the MSP "
            "and the SLA penalties (spec 12.1, spec 12.2)."
        ),
        formula="margin = revenue_total - cost_total",
        unit="EUR",
        aggregation="SUM over the selected months",
        dataset="marge_client_mois",
        fields=("revenue_total", "cost_total", "margin"),
        synonyms=MARGIN_SYNONYMS,
    ),
    _metric(
        name="margin_rate",
        label="Margin rate",
        definition=(
            "Share of the revenue left as margin. A month whose data coverage is below 80 % is an "
            "estimate and must be labelled as such (spec 12.3, spec 12.4)."
        ),
        formula="margin_rate = margin / revenue_total (0 when revenue is 0)",
        unit="ratio",
        aggregation="revenue-weighted average over the selected months",
        dataset="marge_client_mois",
        fields=("margin", "revenue_total", "margin_rate", "is_estimate"),
        synonyms=("rentabilite", "taux de marge"),
    ),
    _metric(
        name="revenue_total",
        label="Revenue",
        definition="Everything invoiced to the client for the month (spec 12.1).",
        formula="revenue_total = revenue_subscription + revenue_aws_resale"
        " + revenue_extra_hours_billed + revenue_projects",
        unit="EUR",
        aggregation="SUM",
        dataset="marge_client_mois",
        fields=(
            "revenue_subscription",
            "revenue_aws_resale",
            "revenue_extra_hours_billed",
            "revenue_projects",
        ),
    ),
    _metric(
        name="cost_total",
        label="Cost",
        definition="Everything the MSP spent to serve the client for the month (spec 12.2).",
        formula="cost_total = cost_labour + cost_tooling + cost_msp_aws + cost_penalties",
        unit="EUR",
        aggregation="SUM",
        dataset="marge_client_mois",
        fields=("cost_labour", "cost_tooling", "cost_msp_aws", "cost_penalties"),
    ),
    _metric(
        name="effort_hours",
        label="Effort",
        definition=(
            "Hours actually spent on the client, split by work category and by level. "
            "Levels only: no person is ever named (ENF-CONF-01, ENF-CONF-02)."
        ),
        formula="effort_hours = SUM(hours_spent) per (client, month, category, level)",
        unit="hours",
        aggregation="SUM",
        dataset="effort_client_mois_categorie",
        fields=("hours_spent", "category", "level"),
        synonyms=("charge", "temps passe"),
    ),
    _metric(
        name="effort_cost",
        label="Effort cost",
        definition="Labour cost of the effort, computed from the hourly cost in force that month.",
        formula="effort_cost = SUM(hours_spent * hourly_cost)",
        unit="EUR",
        aggregation="SUM",
        dataset="effort_client_mois_categorie",
        fields=("labour_cost", "hourly_cost"),
    ),
    _metric(
        name="cost_per_ticket",
        label="Cost per ticket",
        definition="Labour cost of the client divided by the number of tickets handled.",
        formula="cost_per_ticket = labour_cost / ticket_count",
        unit="EUR",
        aggregation="revenue-weighted average",
        dataset="effort_client_mois_categorie",
        fields=("labour_cost", "ticket_count"),
    ),
    _metric(
        name="unbilled_hours",
        label="Unbilled hours",
        definition=(
            "Hours worked for the client that are not on an invoice: validated out-of-scope hours "
            "plus hours above the quota, minus the extra hours already billed (spec 12.3)."
        ),
        formula="unbilled_hours = out_of_scope_validated_hours + over_quota_hours - billed_extra_hours",
        unit="hours",
        aggregation="SUM",
        dataset="heures_non_facturees",
        fields=(
            "out_of_scope_validated_hours",
            "over_quota_hours",
            "billed_extra_hours",
            "unbilled_hours",
        ),
        synonyms=("heures non facturees", "travail offert"),
    ),
    _metric(
        name="unbilled_value",
        label="Value of the unbilled hours",
        definition="What the unbilled hours represent at the contractual hourly rate.",
        formula="unbilled_value = unbilled_hours * contract_hour_rate",
        unit="EUR",
        aggregation="SUM",
        dataset="heures_non_facturees",
        fields=("unbilled_hours", "contract_hour_rate", "unbilled_value"),
    ),
    _metric(
        name="quota_consumption",
        label="Quota consumption",
        definition="Hours consumed against the hours included in the subscription.",
        formula="quota_consumption = consumed_hours / included_hours_per_month",
        unit="ratio",
        aggregation="average over the selected months",
        dataset="effort_client_mois_categorie",
        fields=("hours_spent",),
    ),
    _metric(
        name="coverage",
        label="Data coverage",
        definition=(
            "Share of the hours attached to a client and to a contract. It is the trust indicator "
            "of every other figure of the dashboard (EF-ADM-02)."
        ),
        formula="coverage = attributed_hours / total_hours",
        unit="ratio",
        aggregation="hours-weighted average",
        dataset="marge_client_mois",
        fields=("coverage",),
    ),
    _metric(
        name="renewal_window",
        label="Renewal window",
        definition="Contracts whose end date falls within the next 90 days.",
        formula="renewal_window = contracts with 0 <= days_to_renewal <= 90",
        unit="count",
        aggregation="COUNT DISTINCT contract_id",
        dataset="contrats_actifs",
        fields=("contract_id", "days_to_renewal", "trend", "margin_rate_six_months"),
    ),
)

_SYNONYMS: tuple[SynonymSpec, ...] = (
    SynonymSpec("rentabilite", "margin", "French business word for profitability."),
    SynonymSpec("marge", "margin", "Short form used by the direction."),
    SynonymSpec("ce que le client rapporte", "margin", "Colloquial phrasing used in meetings."),
    SynonymSpec("profit", "margin", "English word used by the international accounts."),
    SynonymSpec("margin", "margin", "English word, same metric as the French ones."),
    SynonymSpec("taux de marge", "margin_rate", "The share of the revenue left as margin."),
    SynonymSpec("heures non facturees", "unbilled_hours", "Work given without being invoiced."),
    SynonymSpec("travail offert", "unbilled_hours", "Same idea, informal wording."),
    SynonymSpec("effort", "effort_hours", "Hours spent on the client."),
    SynonymSpec("charge", "effort_hours", "Same idea, informal wording."),
    SynonymSpec("temps passe", "effort_hours", "Same idea, informal wording."),
)

_JOINS: tuple[JoinSpec, ...] = (
    JoinSpec(
        left="marge_client_mois",
        right="effort_client_mois_categorie",
        on=("client_id", "month"),
        cardinality="one to many",
        purpose="Explain the margin of a client-month with the effort behind it.",
    ),
    JoinSpec(
        left="marge_client_mois",
        right="heures_non_facturees",
        on=("client_id", "month"),
        cardinality="one to one",
        purpose="Attach the unbilled hours to the margin of the same client-month.",
    ),
    JoinSpec(
        left="marge_client_mois",
        right="contrats_actifs",
        on=("client_id",),
        cardinality="one to many",
        purpose="Show the renewal date and the six-month trend next to the margin.",
    ),
    JoinSpec(
        left="marge_client_mois",
        right="interventions_a_valider",
        on=("client_id",),
        cardinality="one to many",
        purpose="Show the classifications still waiting for a human on that client.",
    ),
    JoinSpec(
        left="heures_non_facturees",
        right="contrats_actifs",
        on=("client_id",),
        cardinality="many to one",
        purpose="Value the unbilled hours with the contractual rate of the active contract.",
    ),
)

_DEFAULT_AGGREGATIONS: tuple[str, ...] = (
    "EUR and hour measures are summed over the selected period",
    "margin_rate is a revenue-weighted average, never a mean of monthly rates",
    "coverage is an hours-weighted average",
    "cost_per_ticket is a labour-weighted average",
    "counts use COUNT DISTINCT on the contract, the ticket or the intervention",
    "the last refreshed value is kept for contractual fields (end date, rate, quota)",
)

TOPIC: TopicSpec = TopicSpec(
    name="marge_topic",
    description=(
        "Semantic layer of Marge: the definitions of the margin, of the effort and of the "
        "unbilled hours, the business synonyms, the default aggregations and the joins between "
        "the five analytical datasets. Every question about the profitability of a client goes "
        "through this topic so that two people get the same number."
    ),
    metrics=_METRICS,
    synonyms=_SYNONYMS,
    joins=_JOINS,
    datasets=DATASET_NAMES,
    default_aggregations=_DEFAULT_AGGREGATIONS,
    requirement="EF-AGT-01, spec 14.1",
)
