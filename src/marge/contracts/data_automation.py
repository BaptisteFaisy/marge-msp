"""Bedrock Data Automation client for contract reading (EF-CTR-01, spec 13.1).

Call sequence, checked against the ``bedrock-data-automation-runtime`` service
model on 2026-11-11:

1. ``InvokeDataAutomationAsync`` with ``inputConfiguration.s3Uri`` (the PDF),
   ``outputConfiguration.s3Uri`` (where the result lands), the project ARN built
   from the Annex B blueprint, and a **data automation profile ARN** — an
   ``arn:aws:bedrock:<region>:aws:data-automation-profile/...``, not the project
   ARN; the service rejects anything else.
2. ``GetDataAutomationStatus`` until the invocation leaves ``Created`` /
   ``InProgress``.
3. Read the result JSON from the output location and map it onto Annex B.

boto3 is imported inside the methods: the CI workers do not have it.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from ..domain import ContractFields, SourceSpan
from .schema import to_contract_fields

PROFILE_TEMPLATE = "arn:aws:bedrock:{region}:aws:data-automation-profile/us.data-automation-v1"
TERMINAL_STATES = ("Success", "ServiceError", "ClientError")


class DataAutomationError(RuntimeError):
    """Raised when the invocation fails or never completes."""


@dataclass(slots=True)
class BedrockDataAutomation:
    """Extracts the Annex B fields of a contract with Bedrock Data Automation."""

    project_arn: str = ""
    region: str = "eu-west-1"
    output_bucket: str = ""
    output_prefix: str = "contracts-output"
    stage: str = "LIVE"
    poll_seconds: float = 2.0
    max_wait_seconds: float = 120.0
    client: Any = None
    s3_client: Any = None
    last_invocation: dict[str, Any] = field(default_factory=dict)

    @property
    def profile_arn(self) -> str:
        return PROFILE_TEMPLATE.format(region=self.region)

    def _runtime(self) -> Any:
        if self.client is None:
            import boto3

            self.client = boto3.client("bedrock-data-automation-runtime", region_name=self.region)
        return self.client

    def _s3(self) -> Any:
        if self.s3_client is None:
            import boto3

            self.s3_client = boto3.client("s3", region_name=self.region)
        return self.s3_client

    def extract(self, document_key: str, content: bytes = b"") -> ContractFields:
        """Read one contract; ``content`` is ignored, the service reads S3."""
        source = _as_s3_uri(document_key, self.output_bucket)
        output = self._output_uri(source)
        invocation = self._invoke(source, output)
        self.last_invocation = invocation
        status = self._await(invocation["invocationArn"])
        payload = self._read_result(status)
        fields = to_contract_fields(_flatten_fields(payload))
        fields.spans = _spans_of(payload)
        return fields

    def _output_uri(self, source: str) -> str:
        bucket = self.output_bucket or source.split("/")[2]
        stem = source.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        return f"s3://{bucket}/{self.output_prefix.strip('/')}/{stem}/"

    def _invoke(self, source: str, output: str) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "inputConfiguration": {"s3Uri": source},
            "outputConfiguration": {"s3Uri": output},
            "dataAutomationProfileArn": self.profile_arn,
        }
        if self.project_arn:
            kwargs["dataAutomationConfiguration"] = {
                "dataAutomationProjectArn": self.project_arn,
                "stage": self.stage,
            }
        return self._runtime().invoke_data_automation_async(**kwargs)

    def _await(self, invocation_arn: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.max_wait_seconds
        while True:
            status = self._runtime().get_data_automation_status(invocationArn=invocation_arn)
            state = status.get("status", "")
            if state in TERMINAL_STATES:
                if state != "Success":
                    raise DataAutomationError(f"{state}: {status.get('errorMessage', '')}")
                return status
            if time.monotonic() > deadline:
                raise DataAutomationError(f"still {state} after {self.max_wait_seconds}s")
            time.sleep(self.poll_seconds)

    def _read_result(self, status: dict[str, Any]) -> dict[str, Any]:
        uri = (status.get("outputConfiguration") or {}).get("s3Uri", "")
        bucket, prefix = _split_s3_uri(uri)
        listed = self._s3().list_objects_v2(Bucket=bucket, Prefix=prefix)
        keys = [item["Key"] for item in listed.get("Contents", []) if item["Key"].endswith(".json")]
        if not keys:
            raise DataAutomationError(f"no JSON result under {uri}")
        body = self._s3().get_object(Bucket=bucket, Key=sorted(keys)[-1])["Body"].read()
        return json.loads(body)


def _as_s3_uri(document_key: str, default_bucket: str) -> str:
    if document_key.startswith("s3://"):
        return document_key
    if not default_bucket:
        raise DataAutomationError("a bare key needs an output_bucket to build the s3 URI")
    return f"s3://{default_bucket}/{document_key.lstrip('/')}"


def _split_s3_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise DataAutomationError(f"not an s3 URI: {uri!r}")
    bucket, _, key = uri[len("s3://") :].partition("/")
    return bucket, key


def _flatten_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Blueprint output -> ``{snake_case_field: value}``.

    The service answers with the UPPER_SNAKE names of the blueprint, either flat
    or nested under an analysis envelope; both shapes are accepted, and every
    value keeps only its text so ``to_contract_fields`` does the typing.
    """
    source = payload
    for key in ("analysis", "result", "document", "extractedFields", "customOutput"):
        if isinstance(source, dict) and key in source and isinstance(source[key], dict):
            source = source[key]
    flat: dict[str, Any] = {}
    for name, value in source.items() if isinstance(source, dict) else []:
        flat[name.lower()] = _value_of(value)
    return flat


def _value_of(value: Any) -> Any:
    if isinstance(value, dict):
        for key in ("value", "text", "content", "extractedValue"):
            if key in value:
                return _value_of(value[key])
        return value
    if isinstance(value, list):
        return [_value_of(item) for item in value]
    return value


def _spans_of(payload: dict[str, Any]) -> dict[str, SourceSpan]:
    """EF-CTR-02: the passage each extracted value was read from."""
    spans: dict[str, SourceSpan] = {}
    for name, value in _walk_for_spans(payload):
        quote = str(value.get("text") or value.get("value") or value.get("content") or "")
        spans[name.lower()] = SourceSpan(
            quote=quote[:400],
            page=value.get("page") or value.get("pageNumber"),
            char_start=value.get("beginOffset") or value.get("start"),
            char_end=value.get("endOffset") or value.get("end"),
        )
    return spans


_SPAN_MARKERS = ("beginOffset", "endOffset", "boundingBox", "page", "pageNumber")


def _walk_for_spans(node: Any, path: str = "") -> list[tuple[str, dict]]:
    """Every node carrying a position, tagged with its own field name.

    The key of the node *is* the field name, so it replaces ``path`` on the way
    down: keeping the ancestor name would collapse every span onto the envelope
    key and the portal would show one quote for all fields.
    """
    found: list[tuple[str, dict]] = []
    if isinstance(node, dict):
        if any(marker in node for marker in _SPAN_MARKERS):
            found.append((path or "value", node))
            return found
        for key, value in node.items():
            found.extend(_walk_for_spans(value, key))
    elif isinstance(node, list):
        for item in node:
            found.extend(_walk_for_spans(item, path))
    return found
