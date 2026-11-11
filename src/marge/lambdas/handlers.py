"""Lambda handlers: thin adapters over the real application code.

Nothing here holds business logic. Each handler builds (or reuses) the objects
of ``marge`` and delegates: the portal serves the very same FastAPI app as
``marge serve``, the contract reader calls the very same extractor as the CLI,
the MCP handler calls the very same ``handle_request`` as the stdio server.

Environment (set by the CDK stacks):
``MARGE_TABLE`` DynamoDB table, ``MARGE_REGION``, ``MARGE_AUTH_MODE``,
``MARGE_PORTAL_DIR``, ``MARGE_PROFILE_ARN`` (Bedrock Data Automation project).
"""

from __future__ import annotations

import json
import os
from typing import Any

from .asgi import handle as asgi_handle

_APP: Any = None
_STORE: Any = None


def _store() -> Any:
    """The DynamoDB store, created once per warm container."""
    global _STORE
    if _STORE is None:
        from ..store.dynamo_store import DynamoStore

        _STORE = DynamoStore(
            table_name=os.environ.get("MARGE_TABLE", "marge"),
            region_name=os.environ.get("MARGE_REGION") or None,
        )
    return _STORE


def _app() -> Any:
    """The portal FastAPI app, created once per warm container."""
    global _APP
    if _APP is None:
        from ..api import create_app

        _APP = create_app(
            store=_store(),
            auth_mode=os.environ.get("MARGE_AUTH_MODE", "cognito"),
            portal_dir=os.environ.get("MARGE_PORTAL_DIR") or None,
        )
    return _APP


def portal_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """API Gateway REST proxy entry point of the validation portal."""
    return asgi_handle(_app(), event)


def _classifier():
    """The Bedrock classifier, or the deterministic local rules as a fallback."""
    from ..classify.bedrock import BedrockClassifierModel

    model_id = os.environ.get("MARGE_MODEL_ID", "")
    return BedrockClassifierModel(model_id=model_id) if model_id else BedrockClassifierModel()


def classify_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Classify the interventions of one month that have no classification yet."""
    from ..classify.memory import DecisionMemory
    from ..classify.service import classify
    from ..domain import Month
    from ..pipeline.nightly import classify_pending

    store = _store()
    month = Month.parse(event["month"]) if event.get("month") else None
    if month is None:
        return {"classified": 0, "detail": "no month given"}

    model = _classifier()
    memory = DecisionMemory(store)

    def run(intervention, contract):
        return classify(intervention, contract, model, store.load(), memory=memory)

    classified, reused, queued = classify_pending(store, store.load(), month, run)
    return {"month": str(month), "classified": classified, "reused": reused, "queued": queued}


def contracts_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Read one contract document from S3 and store its Annex B fields.

    The extraction runs on Bedrock Data Automation; the contract stays in
    ``EXTRACTED`` status, because only a human validation makes it count
    (EF-CTR-03, ENF-IA-02).
    """
    from ..contracts import extract_fields
    from ..domain import Contract, ContractFields, ContractStatus

    bucket = event["bucket"]
    key = event["key"]
    source = f"s3://{bucket}/{key}"
    extractor = _extractor(bucket)
    if extractor is not None:
        # Bedrock Data Automation lit le document dans S3 lui-même.
        fields = extractor.extract(source)
    else:
        fields = extract_fields(_read_s3(bucket, key), key)

    contract = Contract(
        contract_id=event.get("contract_id") or _contract_id_of(key),
        client_id=event.get("client_id", ""),
        version=int(event.get("version", 1)),
        fields=fields if isinstance(fields, ContractFields) else ContractFields(),
        status=ContractStatus.EXTRACTED,
        document_key=f"s3://{bucket}/{key}",
        effective_from=fields.start_date,
    )
    _store().save_contract(contract)
    return {
        "contract_id": contract.contract_id,
        "version": contract.version,
        "status": contract.status.value,
        "customer_name": fields.customer_name,
        "fields_with_source": sorted(fields.spans),
    }


def _extractor(output_bucket: str):
    """Bedrock Data Automation when a project ARN is configured, else None.

    Without the project ARN the caller falls back to the deterministic local
    extractor, so the offline demo and the CI never need AWS.
    """
    project_arn = os.environ.get("MARGE_PROFILE_ARN", "")
    if not project_arn:
        return None
    from ..contracts.data_automation import BedrockDataAutomation

    return BedrockDataAutomation(
        project_arn=project_arn,
        region=os.environ.get("MARGE_REGION") or "eu-west-1",
        output_bucket=output_bucket,
    )


def _read_s3(bucket: str, key: str) -> bytes:
    import boto3

    return (
        boto3.client("s3", region_name=os.environ.get("MARGE_REGION") or None)
        .get_object(Bucket=bucket, Key=key)["Body"]
        .read()
    )


def _contract_id_of(key: str) -> str:
    name = key.rsplit("/", 1)[-1]
    return name.split("-v")[0].rsplit(".", 1)[0]


def mcp_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Serve the MCP tools over API Gateway / AgentCore Gateway."""
    from ..domain import ActorRole
    from ..mcp import McpContext, handle_request

    payload = _mcp_payload(event)
    ctx = McpContext(
        store=_store(),
        actor_id=event.get("actor_id", os.environ.get("MARGE_ACTOR", "controller-01")),
        role=ActorRole(event.get("role", os.environ.get("MARGE_ROLE", "CONTROLLER"))),
    )
    return handle_request(payload, ctx)


def _mcp_payload(event: dict[str, Any]) -> dict[str, Any]:
    """The JSON-RPC message, whether it comes as a dict or as an API body."""
    if event.get("jsonrpc"):
        return event
    body = event.get("body")
    if isinstance(body, str) and body.strip():
        return json.loads(body)
    if isinstance(body, dict):
        return body
    return event
