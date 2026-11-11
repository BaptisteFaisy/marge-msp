"""The Quick Sight API calls, exercised offline against a recording fake."""

from __future__ import annotations

from typing import Any

import pytest

from marge.quicksight import quick_api

DATA_SOURCE = {
    "aws_account_id": "123456789012",
    "data_source_id": "marge-athena",
    "name": "marge-athena",
    "work_group": "marge",
    "role_arn": "arn:aws:iam::123456789012:role/marge-athena",
    "username": "marge",
    "password": "not-a-real-secret",
}

DATASET = {
    "aws_account_id": "123456789012",
    "dataset_id": "marge_client_mois",
    "data_source_arn": "arn:aws:quicksight:eu-west-3:123456789012:datasource/marge-athena",
    "name": "marge_client_mois",
    "sql": "SELECT client_id, margin FROM marge.marge_mensuelle",
    "columns": [
        {"name": "client_id", "data_type": "string"},
        {"name": "margin", "data_type": "decimal"},
    ],
}

DASHBOARD = {
    "aws_account_id": "123456789012",
    "dashboard_id": "marge-overview",
    "name": "Profitability overview",
    "description": "EF-TDB-01",
    "source_entity": {"SourcePath": "arn:aws:quicksight:eu-west-3:123456789012:dashboard/x"},
}


class RecordingClient:
    """A fake Quick Sight client that records the call it receives."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _record(self, name: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, kwargs))
        return {"ok": True, "call": name}

    def create_data_source(self, **kwargs: Any) -> dict[str, Any]:
        return self._record("create_data_source", kwargs)

    def create_data_set(self, **kwargs: Any) -> dict[str, Any]:
        return self._record("create_data_set", kwargs)

    def update_data_set(self, **kwargs: Any) -> dict[str, Any]:
        return self._record("update_data_set", kwargs)

    def create_topic_v2(self, **kwargs: Any) -> dict[str, Any]:
        return self._record("create_topic_v2", kwargs)

    def create_dashboard(self, **kwargs: Any) -> dict[str, Any]:
        return self._record("create_dashboard", kwargs)

    def create_agent(self, **kwargs: Any) -> dict[str, Any]:
        return self._record("create_agent", kwargs)

    def create_flow(self, **kwargs: Any) -> dict[str, Any]:
        return self._record("create_flow", kwargs)

    def create_space(self, **kwargs: Any) -> dict[str, Any]:
        return self._record("create_space", kwargs)


@pytest.fixture
def api() -> RecordingClient:
    return RecordingClient()


def test_create_data_source_uses_athena(api: RecordingClient) -> None:
    quick_api.create_data_source(api, DATA_SOURCE)
    name, kwargs = api.calls[0]
    assert name == "create_data_source"
    assert kwargs["Type"] == "ATHENA"
    assert kwargs["DataSourceParameters"]["AthenaParameters"]["WorkGroup"] == "marge"


def test_create_dataset_maps_the_types_of_annex_a(api: RecordingClient) -> None:
    quick_api.create_dataset(api, DATASET)
    _, kwargs = api.calls[0]
    schema = kwargs["DataSetSchema"]["ColumnSchemaList"]
    assert {"ColumnName": "client_id", "DataType": "STRING"} in schema
    assert {"ColumnName": "margin", "DataType": "DECIMAL"} in schema


def test_create_dataset_loads_into_spice(api: RecordingClient) -> None:
    quick_api.create_dataset(api, DATASET)
    _, kwargs = api.calls[0]
    assert kwargs["ImportMode"] == "SPICE"
    assert kwargs["PhysicalTableMap"]["marge_client_mois"]["CustomSQL"]["SqlQuery"] == DATASET["sql"]


def test_create_topic_declares_its_datasets(api: RecordingClient) -> None:
    quick_api.create_topic(
        api,
        {
            "aws_account_id": "123456789012",
            "topic_id": "marge_topic",
            "name": "marge_topic",
            "description": "Semantic layer",
            "datasets": [{"DataSetArn": "arn:aws:quicksight:::dataset/a", "DataSetName": "a"}],
        },
    )
    name, kwargs = api.calls[0]
    assert name == "create_topic_v2"
    assert kwargs["Topic"]["DataSets"][0]["DataSetName"] == "a"


def test_create_dashboard_passes_its_source_entity(api: RecordingClient) -> None:
    quick_api.create_dashboard(api, DASHBOARD)
    _, kwargs = api.calls[0]
    assert kwargs["DashboardId"] == "marge-overview"
    assert "SourcePath" in kwargs["SourceEntity"]


def test_create_agent_passes_the_instructions(api: RecordingClient) -> None:
    quick_api.create_agent(
        api,
        {
            "aws_account_id": "123456789012",
            "agent_id": "marge-profitability-agent",
            "name": "Profitability analyst",
            "instructions": "Never estimate a figure.",
        },
    )
    name, kwargs = api.calls[0]
    assert name == "create_agent"
    assert "Never estimate a figure." in kwargs["Instructions"]


def test_create_flow_passes_the_owner_and_the_sources(api: RecordingClient) -> None:
    quick_api.create_flow(
        api,
        {
            "aws_account_id": "123456789012",
            "flow_id": "FLOW-MONTHLY-REVIEW",
            "name": "Monthly profitability review",
            "owner": "controller",
            "sources": ["EF-TDB-01"],
            "destination": "email",
        },
    )
    _, kwargs = api.calls[0]
    assert kwargs["Owner"] == "controller"
    assert kwargs["Sources"] == ["EF-TDB-01"]


def test_create_space_is_private(api: RecordingClient) -> None:
    quick_api.create_space(
        api,
        {
            "aws_account_id": "123456789012",
            "space_id": "marge_project",
            "name": "Marge project",
        },
    )
    _, kwargs = api.calls[0]
    assert kwargs["SpaceType"] == "PRIVATE"


def test_apply_rls_updates_the_dataset(api: RecordingClient) -> None:
    quick_api.apply_rls(
        api,
        {
            "aws_account_id": "123456789012",
            "dataset_id": "marge_client_mois",
            "name": "marge_client_mois",
            "permission_set": "arn:aws:quicksight:::dataset/rls",
            "dataset_reference": "marge_client_mois",
        },
    )
    name, kwargs = api.calls[0]
    assert name == "update_data_set"
    assert "RowLevelPermissionDataSet" in kwargs


def test_every_type_of_annex_a_has_a_quick_type() -> None:
    from marge.quicksight import DATASETS

    for dataset in DATASETS:
        for field in dataset.fields:
            assert field.data_type in quick_api.QUICK_TYPE
