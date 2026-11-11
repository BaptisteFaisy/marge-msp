"""Single-table schema description shared by the store and the CDK stack.

Split out of ``dynamo_store`` so the persistence module stays under the size
limit and the infrastructure reads the very same key design it deploys: one
table, composite key ``(pk, sk)``, three sparse GSIs whose partition value
carries the entity kind (``contracts#CLIENT#c-001``) so one index serves every
entity without collisions.
"""

from __future__ import annotations

from typing import Any

DEFAULT_TABLE_NAME = "marge"

# GSI kind -> (index name, partition attribute). The kind is embedded in the
# GSI partition value ("contracts#CLIENT#c-001") so indexes stay sparse and
# collision-free across entities.
GSI_OF: dict[str, tuple[str, str]] = {
    "CLIENT": ("gsi_client", "client_pk"),
    "MONTH": ("gsi_month", "month_pk"),
    "STATUS": ("gsi_status", "status_pk"),
}


def create_table_resources(table_name: str = DEFAULT_TABLE_NAME) -> dict[str, Any]:
    """Pure-Python table/GSI description for the CDK stack (no network call)."""
    attributes = [{"AttributeName": name, "AttributeType": "S"} for name in ("pk", "sk")]
    attributes += [{"AttributeName": attr, "AttributeType": "S"} for _, attr in GSI_OF.values()]
    gsis = [
        {
            "IndexName": index,
            "KeySchema": [
                {"AttributeName": attr, "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            "Projection": {"ProjectionType": "ALL"},
        }
        for index, attr in GSI_OF.values()
    ]
    return {
        "TableName": table_name,
        "BillingMode": "PAY_PER_REQUEST",
        "PointInTimeRecoverySpecification": {"PointInTimeRecoveryEnabled": True},
        "AttributeDefinitions": attributes,
        "KeySchema": [
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        "GlobalSecondaryIndexes": gsis,
    }
