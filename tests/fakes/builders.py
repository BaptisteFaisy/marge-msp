"""Shared fixture builders.

``golden_*`` reproduce Annex D of docs/SPEC.fr.md exactly:
October 2026, revenue 4 620 EUR, cost 3 725 EUR, margin 895 EUR (19.37 %),
9 validated out-of-scope hours worth 9 x 110 = 990 EUR.

All amounts are expressed in the reporting currency (EUR here): currency
conversion is the job of the billing connector at load time, not of the
calculation (see docs/CONTRACT.md).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from marge.calc import MarginInputs
from marge.domain import (
    AwsCost,
    AwsCostKind,
    Classification,
    Client,
    Contract,
    ContractFields,
    ContractStatus,
    DecisionStatus,
    Intervention,
    Month,
    Rate,
    Settings,
    ToolingCost,
    WorkClass,
    WorkLevel,
)

GOLDEN_MONTH_DATE = date(2026, 10, 15)
GOLDEN_CLIENT_ID = "c-001"


def golden_client() -> Client:
    return Client(
        client_id=GOLDEN_CLIENT_ID,
        name="Durand Industries",
        account_manager_id="am-01",
        sector="industry",
        onboarded_on=date(2024, 3, 1),
        managed_resource_count=40,
    )


def golden_contract() -> Contract:
    fields = ContractFields(
        customer_name="Durand Industries",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        renewal_terms="tacite, 12 mois",
        termination_notice="3 mois",
        monthly_subscription=Decimal("4000"),
        currency="EUR",
        included_hours_per_month=Decimal("50"),
        extra_hour_rate=Decimal("110"),
        services_included=(
            "Supervision 24/7 de l'infrastructure",
            "Sauvegarde et restauration",
            "Patch management des systèmes",
        ),
        exclusions=(
            "les développements applicatifs et la modification du code du Client",
            "la formation des équipes du Client",
        ),
        service_hours="24x7",
    )
    return Contract(
        contract_id="ctr-001",
        client_id=GOLDEN_CLIENT_ID,
        version=1,
        fields=fields,
        status=ContractStatus.VALIDATED,
        document_key="contracts/ctr-001-v1.pdf",
        effective_from=date(2026, 1, 1),
        validated_by="controller-01",
        validated_at=date(2026, 1, 5),
        validation_reason="clauses conformes au PDF",
    )


def golden_rates() -> tuple[Rate, ...]:
    day = date(2026, 1, 1)
    return (
        Rate(level=WorkLevel.N1, hourly_cost=Decimal("50"), effective_from=day),
        Rate(level=WorkLevel.N2, hourly_cost=Decimal("70"), effective_from=day),
        Rate(level=WorkLevel.N3, hourly_cost=Decimal("80"), effective_from=day),
    )


def golden_interventions() -> tuple[Intervention, ...]:
    """55 h total: 31 h N1, 18 h N2, 6 h N3 — 9 h of them out of scope."""
    plan = (
        ("wl-001", "t-1001", WorkLevel.N1, "12", "Supervision", "IN_SCOPE"),
        ("wl-002", "t-1002", WorkLevel.N1, "10", "Sauvegarde", "IN_SCOPE"),
        ("wl-003", "t-1003", WorkLevel.N1, "9", "Patch management", "IN_SCOPE"),
        ("wl-004", "t-1004", WorkLevel.N2, "9", "Incident base de données", "IN_SCOPE"),
        ("wl-005", "t-1005", WorkLevel.N2, "9", "Correctif requête SQL applicative", "OUT_OF_SCOPE"),
        ("wl-006", "t-1006", WorkLevel.N3, "6", "Architecture sauvegarde", "IN_SCOPE"),
    )
    rows: list[Intervention] = []
    for index, (iid, ticket, level, duration, category, _wclass) in enumerate(plan):
        rows.append(
            Intervention(
                intervention_id=iid,
                ticket_id=ticket,
                client_id=GOLDEN_CLIENT_ID,
                occurred_on=date(2026, 10, 5 + index),
                category=category,
                level=level,
                hours_spent=Decimal(duration),
                description=f"{category} — {ticket}",
                aws_account_id="111122223333",
            )
        )
    return tuple(rows)


def golden_classifications() -> tuple[Classification, ...]:
    rows: list[Classification] = []
    for intervention in golden_interventions():
        out = "SQL" in intervention.category or "applicative" in intervention.category
        rows.append(
            Classification(
                intervention_id=intervention.intervention_id,
                client_id=GOLDEN_CLIENT_ID,
                contract_version=1,
                work_class=WorkClass.OUT_OF_SCOPE if out else WorkClass.INCLUDED,
                confidence=Decimal("0.88") if out else Decimal("0.95"),
                cited_clause="Article 3.2 — Exclusions : « les développements applicatifs »",
                reason="application code change",
                billable_hours=intervention.hours_spent,
                needs_human_validation=out,
                status=DecisionStatus.APPROVED if out else DecisionStatus.PENDING,
                decided_by="am-01" if out else None,
                decided_at=date(2026, 10, 20) if out else None,
            )
        )
    return tuple(rows)


def golden_aws_costs() -> tuple[AwsCost, ...]:
    return (
        AwsCost(
            aws_account_id="111122223333",
            month=Month.parse("2026-10"),
            cost=Decimal("3000"),
            kind=AwsCostKind.CLIENT_ACCOUNT,
            client_id=GOLDEN_CLIENT_ID,
            rebilled_amount=Decimal("3620"),
            currency="EUR",
        ),
        AwsCost(
            aws_account_id="999988887777",
            month=Month.parse("2026-10"),
            cost=Decimal("95"),
            kind=AwsCostKind.MSP_TOOLING_ACCOUNT,
            client_id=GOLDEN_CLIENT_ID,
            currency="EUR",
        ),
    )


def golden_tooling() -> tuple[ToolingCost, ...]:
    return (
        ToolingCost(
            tool="supervision-dediee",
            monthly_cost=Decimal("340"),
            client_id=GOLDEN_CLIENT_ID,
        ),
    )


def golden_inputs() -> MarginInputs:
    """The exact Annex D scenario, ready for ``compute_margin_month``."""
    return MarginInputs(
        client=golden_client(),
        month=Month.parse("2026-10"),
        contract=golden_contract(),
        interventions=golden_interventions(),
        classifications=golden_classifications(),
        aws_costs=golden_aws_costs(),
        rates=golden_rates(),
        tooling_costs=golden_tooling(),
        total_msp_hours=Decimal("55"),
        total_managed_resources=40,
        active_client_count=1,
        client_aws_account_count=1,
        calculation_version=1,
    )


def golden_settings() -> Settings:
    return Settings()
