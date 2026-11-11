"""Shared fixtures for the API tests (offline, deterministic).

The store is a ``FakeStore`` seeded with two clients managed by two different
account managers, so every row-level filtering rule (EF-TDB-06) can be tested.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from tests.fakes.fake_store import FakeStore

from marge.api import create_app
from marge.domain import (
    AllocationBasis,
    Classification,
    Client,
    ClientMatch,
    Contract,
    ContractFields,
    ContractStatus,
    DecisionStatus,
    Intervention,
    Rate,
    Settings,
    SourceKind,
    SourceSpan,
    ToolingCost,
    WorkClass,
    WorkLevel,
)


def make_headers(role: str, actor_id: str | None = None) -> dict[str, str]:
    """Dev-mode auth headers for a role (EF-ADM-03 demo identities)."""
    return {"X-Actor-Id": actor_id or role.lower(), "X-Actor-Role": role}


@pytest.fixture()
def hdr():
    """Fixture wrapper of ``make_headers`` (no package import needed)."""
    return make_headers


def _client_two() -> Client:
    return Client(
        client_id="c-002",
        name="Dupont Logistics",
        account_manager_id="am-02",
        sector="logistics",
        onboarded_on=date(2025, 6, 1),
        managed_resource_count=20,
    )


def _extracted_contract() -> Contract:
    """A contract pending validation, with a source span on one field (EF-CTR-02)."""
    fields = ContractFields(
        customer_name="Dupont Logistics",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        renewal_terms="tacite, 12 mois",
        termination_notice="2 mois",
        monthly_subscription=Decimal("2500"),
        currency="EUR",
        included_hours_per_month=Decimal("30"),
        extra_hour_rate=Decimal("95"),
        services_included=("Supervision 24/7",),
        exclusions=("les développements applicatifs",),
        service_hours="24x7",
    )
    fields.spans["monthly_subscription"] = SourceSpan(
        quote="Le Client paiera la somme de 2 500 EUR par mois", page=1, char_start=120, char_end=168
    )
    return Contract(
        contract_id="ctr-002",
        client_id="c-002",
        version=1,
        fields=fields,
        status=ContractStatus.EXTRACTED,
        document_key="contracts/ctr-002-v1.pdf",
        effective_from=date(2026, 1, 1),
    )


def _interventions() -> tuple[Intervention, ...]:
    return (
        Intervention(
            intervention_id="wl-101",
            ticket_id="t-2001",
            client_id="c-002",
            occurred_on=date(2026, 10, 6),
            category="Developpement specifique",
            level=WorkLevel.N2,
            hours_spent=Decimal("4"),
            description="SQL query fix in the client application",
        ),
        Intervention(
            intervention_id="wl-102",
            ticket_id="t-2002",
            client_id="c-002",
            occurred_on=date(2026, 10, 7),
            category="Supervision",
            level=WorkLevel.N1,
            hours_spent=Decimal("2"),
            description="Monitoring alert follow-up",
        ),
    )


def _classifications() -> tuple[Classification, ...]:
    return (
        Classification(
            intervention_id="wl-101",
            client_id="c-002",
            contract_version=1,
            work_class=WorkClass.OUT_OF_SCOPE,
            confidence=Decimal("0.86"),
            cited_clause="Article 3.2 — Exclusions : « les développements applicatifs »",
            reason="application code change",
            billable_hours=Decimal("4"),
            needs_human_validation=True,
            status=DecisionStatus.PENDING,
        ),
        Classification(
            intervention_id="wl-102",
            client_id="c-002",
            contract_version=1,
            work_class=WorkClass.UNCERTAIN,
            confidence=Decimal("0.42"),
            cited_clause="",
            reason="low confidence",
            billable_hours=Decimal("2"),
            needs_human_validation=True,
            status=DecisionStatus.PENDING,
        ),
    )


@pytest.fixture()
def store() -> FakeStore:
    from tests.fakes.builders import golden_client, golden_contract, golden_rates

    seeded = FakeStore()
    seeded.upsert_clients([golden_client(), _client_two()])
    seeded.save_contract(golden_contract())
    seeded.save_contract(_extracted_contract())
    seeded.save_matches(
        [
            ClientMatch(
                match_id="m-001",
                client_id="c-001",
                source=SourceKind.ITSM,
                source_id="DURIND",
                confidence=Decimal("0.93"),
            ),
            ClientMatch(
                match_id="m-002",
                client_id="c-002",
                source=SourceKind.BILLING,
                source_id="444455556666",
                confidence=Decimal("0.71"),
            ),
        ]
    )
    seeded.save_interventions(_interventions())
    for classification in _classifications():
        seeded.save_classification(classification)
    seeded.save_rates(golden_rates())
    seeded.save_tooling_costs(
        [
            ToolingCost(
                tool="supervision", monthly_cost=Decimal("1200"), basis=AllocationBasis.PER_LABOUR_HOUR
            ),
            ToolingCost(
                tool="backup-dedie",
                monthly_cost=Decimal("340"),
                basis=AllocationBasis.PER_CLIENT,
                client_id="c-002",
            ),
        ]
    )
    return seeded


@pytest.fixture()
def client(store: FakeStore) -> TestClient:
    return TestClient(create_app(store, Settings()))


@pytest.fixture()
def golden_store() -> FakeStore:
    """The exact Annex D scenario, ready for the recalculation endpoint."""
    from tests.fakes.builders import (
        golden_aws_costs,
        golden_classifications,
        golden_client,
        golden_contract,
        golden_interventions,
        golden_rates,
        golden_tooling,
    )

    seeded = FakeStore()
    seeded.upsert_clients([golden_client()])
    seeded.save_contract(golden_contract())
    seeded.save_interventions(golden_interventions())
    for classification in golden_classifications():
        seeded.save_classification(classification)
    seeded.save_rates(golden_rates())
    seeded.save_tooling_costs(golden_tooling())
    seeded.save_aws_costs(golden_aws_costs())
    return seeded


@pytest.fixture()
def golden_client_api(golden_store: FakeStore) -> TestClient:
    return TestClient(create_app(golden_store, Settings()))


def rate_row(level: WorkLevel, cost: str, effective: str = "2026-01-01") -> Rate:
    return Rate(level=level, hourly_cost=Decimal(cost), effective_from=date.fromisoformat(effective))
