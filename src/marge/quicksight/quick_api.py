"""The Quick Sight API calls of the deployment (spec 11.2, spec 14).

One thin function per API call, so that ``deploy`` reads as the ordered
sequence of what gets created and each call stays testable with a fake
client.

``boto3`` is imported inside :func:`client`, never at module level: the test
suite never needs it (docs/CONTRACT.md rule 4).
"""

from __future__ import annotations

from typing import Any

from .assets import DEFAULT_REGION

__all__ = [
    "apply_rls",
    "client",
    "create_agent",
    "create_dashboard",
    "create_data_source",
    "create_dataset",
    "create_flow",
    "create_space",
    "create_topic",
]

QUICK_TYPE: dict[str, str] = {
    "string": "STRING",
    "decimal": "DECIMAL",
    "integer": "INTEGER",
    "boolean": "BOOLEAN",
    "date": "DATETIME",
}
"""Mapping from the types of Annex A to the types of the Quick Sight API."""


def client(region: str | None = None) -> Any:
    """Build a boto3 Quick Sight client (boto3 imported here, never at module level)."""
    import boto3

    return boto3.client("quicksight", region_name=region or DEFAULT_REGION)


def create_data_source(api: Any, spec: dict[str, Any]) -> dict[str, Any]:
    """Create the Athena data source that feeds the five datasets."""
    return api.create_data_source(
        AwsAccountId=spec["aws_account_id"],
        DataSourceId=spec.get("data_source_id", "marge-athena"),
        Name=spec.get("name", "marge-athena"),
        Type="ATHENA",
        DataSourceParameters={
            "AthenaParameters": {
                "WorkGroup": spec.get("work_group", "primary"),
                "RoleArn": spec["role_arn"],
            }
        },
        DataSourceCredentials={
            "CredentialPair": {
                "Username": spec["username"],
                "Password": spec["password"],
            }
        },
    )


def create_dataset(api: Any, spec: dict[str, Any]) -> dict[str, Any]:
    """Create one dataset from its Athena query, with its declared schema."""
    return api.create_data_set(
        AwsAccountId=spec["aws_account_id"],
        DataSetId=spec["dataset_id"],
        Name=spec["name"],
        PhysicalTableMap={
            spec["dataset_id"]: {
                "CustomSQL": {
                    "DataSourceArn": spec["data_source_arn"],
                    "Name": spec["name"],
                    "SqlQuery": spec["sql"],
                }
            }
        },
        LogicalTableMap={
            spec["dataset_id"]: {
                "Alias": spec["name"],
                "Source": {"PhysicalTableId": spec["dataset_id"]},
            }
        },
        DataSetSchema={
            "ColumnSchemaList": [
                {"ColumnName": column["name"], "DataType": QUICK_TYPE[column["data_type"]]}
                for column in spec["columns"]
            ]
        },
        ImportMode="SPICE",
    )


def create_topic(api: Any, spec: dict[str, Any]) -> dict[str, Any]:
    """Create the semantic layer (the Quick topic, ``CreateTopicV2``)."""
    return api.create_topic_v2(
        AwsAccountId=spec["aws_account_id"],
        TopicId=spec["topic_id"],
        Topic={
            "Name": spec["name"],
            "Description": spec.get("description", ""),
            "DataSets": spec["datasets"],
            "DataSetRelations": spec.get("relations", []),
        },
        CustomInstructions={
            "CustomInstructionsString": spec.get("custom_instructions", ""),
        },
    )


def create_dashboard(api: Any, spec: dict[str, Any]) -> dict[str, Any]:
    """Create one dashboard from its source entity."""
    return api.create_dashboard(
        AwsAccountId=spec["aws_account_id"],
        DashboardId=spec["dashboard_id"],
        Name=spec["name"],
        Description=spec.get("description", ""),
        SourceEntity=spec["source_entity"],
    )


def create_agent(api: Any, spec: dict[str, Any]) -> dict[str, Any]:
    """Create the chat agent of EF-AGT-01..03."""
    return api.create_agent(
        AwsAccountId=spec["aws_account_id"],
        AgentId=spec["agent_id"],
        Name=spec["name"],
        Description=spec.get("description", ""),
        Instructions=spec["instructions"],
        KnowledgeBases=spec.get("knowledge_bases", []),
        Tools=spec.get("tools", []),
    )


def create_flow(api: Any, spec: dict[str, Any]) -> dict[str, Any]:
    """Create the scheduled review flow of EF-REV-01."""
    return api.create_flow(
        AwsAccountId=spec["aws_account_id"],
        FlowId=spec["flow_id"],
        Name=spec["name"],
        Description=spec.get("description", ""),
        Owner=spec["owner"],
        Sources=spec["sources"],
        Destination=spec["destination"],
    )


def create_space(api: Any, spec: dict[str, Any]) -> dict[str, Any]:
    """Create the project space that holds the contracts (EF-AGT-01)."""
    return api.create_space(
        AwsAccountId=spec["aws_account_id"],
        SpaceId=spec["space_id"],
        Name=spec["name"],
        Description=spec.get("description", ""),
        SpaceType="PRIVATE",
        Memberships=spec.get("memberships", []),
    )


def apply_rls(api: Any, spec: dict[str, Any]) -> dict[str, Any]:
    """Attach a row-level permission to a dataset (EF-TDB-06)."""
    return api.update_data_set(
        AwsAccountId=spec["aws_account_id"],
        DataSetId=spec["dataset_id"],
        Name=spec["name"],
        RowLevelPermissionDataSet={
            "RowLevelPermissionSet": spec["permission_set"],
            "DataSetReference": spec["dataset_reference"],
        },
        ImportMode="SPICE",
    )
