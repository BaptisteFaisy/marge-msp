"""Offline tests for ``marge.store.dynamo_store`` using an in-memory fake client."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from tests.fakes.builders import (
    golden_client,
    golden_contract,
    golden_interventions,
    golden_rates,
)

from marge.domain import (
    AllocationBasis,
    AwsCost,
    CategoryDecision,
    Classification,
    Client,
    ClientMatch,
    Contract,
    ContractFields,
    ContractStatus,
    CostBreakdown,
    Coverage,
    DecisionStatus,
    EffortSlice,
    HoursSummary,
    Invoice,
    InvoiceKind,
    MarginLine,
    MarginMonth,
    Month,
    Penalty,
    RenewalWatch,
    RevenueBreakdown,
    Settings,
    SourceKind,
    ToolingCost,
    WorkClass,
    WorkLevel,
)
from marge.store import DEFAULT_TABLE_NAME, DynamoStore, create_table_resources


class FakeDynamoClient:
    """In-memory subset of boto3's DynamoDB low-level client."""

    def __init__(self, *, page_size: int = 100) -> None:
        self.items: dict[tuple[str, str], dict[str, Any]] = {}
        self.calls: list[str] = []
        self.page_size = page_size

    def put_item(self, *, TableName: str, Item: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(f"put_item:{TableName}")
        self.items[(Item["pk"]["S"], Item["sk"]["S"])] = Item
        return {}

    def batch_write_item(self, *, RequestItems: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        for table, requests in RequestItems.items():
            self.calls.append(f"batch_write_item:{table}:{len(requests)}")
            assert len(requests) <= 25
            for req in requests:
                if "PutRequest" in req:
                    item = req["PutRequest"]["Item"]
                    self.items[(item["pk"]["S"], item["sk"]["S"])] = item
                elif "DeleteRequest" in req:
                    key = req["DeleteRequest"]["Key"]
                    self.items.pop((key["pk"]["S"], key["sk"]["S"]), None)
        return {}

    def get_item(self, *, TableName: str, Key: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(f"get_item:{TableName}")
        item = self.items.get((Key["pk"]["S"], Key["sk"]["S"]))
        return {"Item": item} if item is not None else {}

    def query(self, **kwargs: Any) -> dict[str, Any]:
        index = kwargs.get("IndexName")
        self.calls.append(f"query:{index or 'primary'}")
        values = kwargs["ExpressionAttributeValues"]
        pk_val = values[":pk"]["S"]
        prefix = values[":prefix"]["S"] if ":prefix" in values else None
        attr = _pk_attr_for_index(index)
        matched = [
            item
            for item in sorted(self.items.values(), key=lambda it: (it["pk"]["S"], it["sk"]["S"]))
            if item.get(attr, {}).get("S") == pk_val
            and (prefix is None or item["sk"]["S"].startswith(prefix))
        ]
        start = kwargs.get("ExclusiveStartKey", {}).get("offset", 0)
        end = start + self.page_size
        page = matched[start:end]
        out: dict[str, Any] = {"Items": page}
        if end < len(matched):
            out["LastEvaluatedKey"] = {"offset": end}
        return out


def _pk_attr_for_index(index: str | None) -> str:
    return {
        "gsi_client": "client_pk",
        "gsi_month": "month_pk",
        "gsi_status": "status_pk",
    }.get(index or "", "pk")


@pytest.fixture()
def fake_client() -> FakeDynamoClient:
    return FakeDynamoClient()


@pytest.fixture()
def store(fake_client: FakeDynamoClient) -> DynamoStore:
    return DynamoStore(client=fake_client)


def test_create_table_resources_describes_keys_and_three_gsis() -> None:
    spec = create_table_resources("custom-marge")
    assert spec["TableName"] == "custom-marge"
    assert spec["BillingMode"] == "PAY_PER_REQUEST"
    assert [k["AttributeName"] for k in spec["KeySchema"]] == ["pk", "sk"]
    gsi_names = [g["IndexName"] for g in spec["GlobalSecondaryIndexes"]]
    assert gsi_names == ["gsi_client", "gsi_month", "gsi_status"]


def test_default_table_name_and_injected_client_skip_boto3(
    store: DynamoStore, fake_client: FakeDynamoClient
) -> None:
    assert store.table_name == DEFAULT_TABLE_NAME
    assert store._client is fake_client


def test_client_round_trip_and_account_manager_filter(store: DynamoStore) -> None:
    c1 = golden_client()
    c2 = Client("c-002", "Beta Corp", "am-02", managed_resource_count=12)
    assert store.upsert_clients([c1, c2]) == 2
    loaded = store.get_client("c-001")
    assert loaded is not None and loaded.name == "Calder Logistics"
    assert [c.client_id for c in store.list_clients("am-02")] == ["c-002"]


def test_matches_round_trip_and_pending_gsi_query(store: DynamoStore, fake_client: FakeDynamoClient) -> None:
    m1 = ClientMatch("m-1", "c-001", SourceKind.ITSM, "CALDER", Decimal("0.95"), DecisionStatus.PENDING)
    m2 = ClientMatch("m-2", "c-002", SourceKind.ITSM, "BETA", Decimal("0.99"), DecisionStatus.APPROVED)
    assert store.save_matches([m1, m2]) == 2
    pending = store.list_matches(pending_only=True)
    assert [m.match_id for m in pending] == ["m-1"]
    assert "query:gsi_status" in fake_client.calls
    assert store.get_match("m-2") is not None


def test_contract_versions_active_and_client_gsi(store: DynamoStore, fake_client: FakeDynamoClient) -> None:
    v1 = golden_contract()
    v2 = Contract(
        "ctr-001",
        "c-001",
        2,
        ContractFields(monthly_subscription=Decimal("4500")),
        ContractStatus.EXTRACTED,
        effective_from=date(2026, 7, 1),
    )
    store.save_contract(v1)
    store.save_contract(v2)
    assert store.get_contract("ctr-001", version=1) is not None
    assert store.get_contract("ctr-001").version == 2
    active = store.active_contract("c-001", Month.parse("2026-10"))
    assert active is not None and active.version == 1
    assert "query:gsi_client" in fake_client.calls


def test_interventions_batch_over_25_and_month_filter(
    store: DynamoStore, fake_client: FakeDynamoClient
) -> None:
    base = golden_interventions()[0]
    many = [
        base.__class__(
            intervention_id=f"wl-{idx:03d}",
            ticket_id=f"t-{idx:03d}",
            client_id="c-001" if idx % 2 == 0 else "c-002",
            occurred_on=date(2026, 10, 5),
            category="Supervision",
            level=WorkLevel.N1,
            hours_spent=Decimal("1.5"),
        )
        for idx in range(30)
    ]
    assert store.save_interventions(many) == 30
    oct_c1 = store.list_interventions(month=Month.parse("2026-10"), client_id="c-001")
    assert len(oct_c1) == 15
    assert "query:gsi_month" in fake_client.calls
    assert any(c.startswith("batch_write_item:marge:25") for c in fake_client.calls)


def test_classifications_and_category_decision_round_trip(store: DynamoStore) -> None:
    store.save_interventions(golden_interventions())
    cls = Classification(
        intervention_id="wl-001",
        client_id="c-001",
        contract_version=1,
        work_class=WorkClass.OUT_OF_SCOPE,
        confidence=Decimal("0.88"),
        status=DecisionStatus.PENDING,
    )
    store.save_classification(cls)
    found = store.list_classifications(status="PENDING", client_id="c-001", month=Month.parse("2026-10"))
    assert len(found) == 1
    assert found[0].confidence == Decimal("0.88")
    decision = CategoryDecision(
        contract_id="ctr-001",
        contract_version=1,
        category="Sauvegarde",
        work_class=WorkClass.INCLUDED,
        decided_by="ctrl-01",
        decided_at=date(2026, 10, 20),
        reason="included in the contract perimeter",
    )
    store.save_category_decision(decision)
    assert store.find_category_decision("ctr-001", 1, "Sauvegarde") is not None


def test_costs_invoices_and_penalties_round_trip(store: DynamoStore) -> None:
    oct_m = Month.parse("2026-10")
    store.save_rates(golden_rates())
    assert len(store.list_rates()) == 3
    store.save_tooling_costs([ToolingCost("sup", Decimal("1200"), basis=AllocationBasis.PER_LABOUR_HOUR)])
    assert store.list_tooling_costs()[0].monthly_cost == Decimal("1200.00")
    store.save_aws_costs([AwsCost("111", oct_m, Decimal("300"), rebilled_amount=Decimal("420"))])
    assert store.list_aws_costs(oct_m)[0].resale_margin == Decimal("120.00")
    store.save_invoices([Invoice("inv-1", "c-001", oct_m, InvoiceKind.EXTRA_HOURS, Decimal("990"))])
    assert store.list_invoices(oct_m)[0].amount == Decimal("990.00")
    store.save_penalties([Penalty("c-001", oct_m, Decimal("50"), "SLA")])
    assert store.list_penalties(oct_m)[0].amount == Decimal("50.00")


def _margin_month(client_id: str, month: Month) -> MarginMonth:
    return MarginMonth(
        client_id=client_id,
        month=month,
        revenue=RevenueBreakdown(subscription=Decimal("1000")),
        costs=CostBreakdown(labour=Decimal("700")),
        coverage=Coverage(total_hours=Decimal("10"), attributed_hours=Decimal("9")),
    )


def _renewal_watch(client_id: str, contract_id: str, days: int) -> RenewalWatch:
    return RenewalWatch(
        client_id=client_id,
        contract_id=contract_id,
        contract_version=1,
        end_date=date(2026, 12, 1),
        days_to_renewal=days,
        monthly_subscription=Decimal("1000"),
        margin_rate_six_months=Decimal("0.2"),
    )


def test_margin_months_paginate_over_small_pages(fake_client: FakeDynamoClient) -> None:
    fake_client.page_size = 2
    store = DynamoStore(client=fake_client)
    oct_m = Month.parse("2026-10")
    store.save_margin_months([_margin_month(f"c-{i:03d}", oct_m) for i in range(5)])
    assert len(store.list_margin_months(month=oct_m)) == 5
    assert len(store.list_margin_months(client_id="c-002")) == 1
    assert store.list_margin_months()[0].margin == Decimal("300.00")


def test_effort_slices_and_hours_summaries_round_trip(store: DynamoStore) -> None:
    oct_m = Month.parse("2026-10")
    store.save_effort_slices(
        [
            EffortSlice(
                client_id="c-001",
                month=oct_m,
                category="Supervision",
                level=WorkLevel.N1,
                hours_spent=Decimal("2"),
                labour_cost=Decimal("100"),
                ticket_count=1,
                work_class=WorkClass.INCLUDED,
            )
        ]
    )
    assert len(store.list_effort_slices("c-001")) == 1
    store.save_hours_summaries(
        [
            HoursSummary(
                client_id="c-001",
                month=oct_m,
                included_quota=Decimal("50"),
                consumed_hours=Decimal("55"),
                out_of_scope_validated_hours=Decimal("3"),
            )
        ]
    )
    assert store.list_hours_summaries("c-001")[0].over_quota_hours == Decimal("5.00")


def test_renewal_watch_is_replaced_and_filtered_by_horizon(store: DynamoStore) -> None:
    store.save_renewal_watch([_renewal_watch("c-001", "ctr-1", 30)])
    store.save_renewal_watch([_renewal_watch("c-002", "ctr-2", 150)])
    assert [w.contract_id for w in store.list_renewal_watch(horizon_days=90)] == []
    assert [w.contract_id for w in store.list_renewal_watch(horizon_days=200)] == ["ctr-2"]


def test_margin_lines_and_settings_audit(store: DynamoStore) -> None:
    oct_m = Month.parse("2026-10")
    store.save_margin_lines("c-001", oct_m, [MarginLine("cost.labour", "old", Decimal("10"), "itsm", "w1")])
    store.save_margin_lines("c-001", oct_m, [MarginLine("cost.labour", "new", Decimal("25"), "itsm", "w2")])
    lines = store.margin_lines("c-001", oct_m)
    assert [line.amount for line in lines] == [Decimal("25")]
    assert store.load() == Settings()
    store.save(Settings(margin_threshold=Decimal("0.22")), "ctrl-1", "raise bar")
    assert store.load().margin_threshold == Decimal("0.22")
    assert store.list_entries(entity_kind="settings", entity_id="current")[0].author == "ctrl-1"
