"""Bedrock Data Automation client: real call sequence, tested with fakes.

The shapes asserted here are the ones the service model imposes (verified on
2026-11-11): full ``s3://`` URIs, an ``data-automation-profile`` ARN that is
*not* the project ARN, and a status poll until ``Success``.
"""

from __future__ import annotations

import json

import pytest

from marge.contracts import BedrockDataAutomation, DataAutomationError

PROJECT = "arn:aws:bedrock:eu-west-1:710332178565:data-automation-project/marge-contracts"
RESULT = {
    "analysis": {
        "CUSTOMER_NAME": {"value": "Calder Logistics", "beginOffset": 12, "endOffset": 40, "page": 1},
        "MONTHLY_SUBSCRIPTION": {"value": "4 000,00 EUR", "beginOffset": 900, "page": 2},
        "INCLUDED_HOURS_PER_MONTH": {"value": "50", "page": 2},
        "SERVICES_INCLUDED": {"value": ["Supervision 24/7", "Sauvegarde"], "page": 3},
        "EXCLUSIONS": {"value": ["les développements applicatifs"], "page": 3},
        "START_DATE": {"value": "2026-01-01"},
    }
}


class FakeRuntime:
    """Stands in for bedrock-data-automation-runtime."""

    def __init__(self, states: list[str] | None = None) -> None:
        self.states = states or ["InProgress", "Success"]
        self.calls: list[dict] = []
        self.invocations: list[str] = []

    def invoke_data_automation_async(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        arn = "arn:aws:bedrock:eu-west-1:710332178565:invocation/abc"
        self.invocations.append(arn)
        return {"invocationArn": arn}

    def get_data_automation_status(self, invocationArn: str) -> dict:
        state = self.states.pop(0) if len(self.states) > 1 else self.states[-1]
        return {
            "status": state,
            "outputConfiguration": {"s3Uri": "s3://raw-bucket/contracts-output/ctr-001-v1/"},
        }


class FakeS3:
    def __init__(self, payload: dict | None = None, keys: list[str] | None = None) -> None:
        self.payload = payload if payload is not None else RESULT
        self.keys = keys if keys is not None else ["contracts-output/ctr-001-v1/result.json"]
        self.gets: list[tuple[str, str]] = []

    def list_objects_v2(self, Bucket: str, Prefix: str) -> dict:
        return {"Contents": [{"Key": key} for key in self.keys if key.startswith(Prefix)]}

    def get_object(self, Bucket: str, Key: str) -> dict:
        self.gets.append((Bucket, Key))

        class _Body:
            def __init__(self, data: bytes) -> None:
                self._data = data

            def read(self) -> bytes:
                return self._data

        return {"Body": _Body(json.dumps(self.payload).encode())}


def _client(runtime=None, s3=None) -> BedrockDataAutomation:
    return BedrockDataAutomation(
        project_arn=PROJECT,
        region="eu-west-1",
        output_bucket="raw-bucket",
        poll_seconds=0,
        client=runtime or FakeRuntime(),
        s3_client=s3 or FakeS3(),
    )


def test_invocation_uses_full_s3_uris() -> None:
    runtime = FakeRuntime()
    _client(runtime=runtime).extract("contracts/ctr-001-v1.pdf")
    call = runtime.calls[0]
    assert call["inputConfiguration"]["s3Uri"] == "s3://raw-bucket/contracts/ctr-001-v1.pdf"
    assert call["outputConfiguration"]["s3Uri"].startswith("s3://raw-bucket/contracts-output/")


def test_profile_arn_is_a_profile_not_the_project() -> None:
    """The service rejects a project ARN in dataAutomationProfileArn."""
    runtime = FakeRuntime()
    client = _client(runtime=runtime)
    client.extract("s3://raw-bucket/contracts/ctr-001-v1.pdf")
    call = runtime.calls[0]
    assert call["dataAutomationProfileArn"] == client.profile_arn
    assert ":data-automation-profile/" in call["dataAutomationProfileArn"]
    assert call["dataAutomationConfiguration"]["dataAutomationProjectArn"] == PROJECT
    assert call["dataAutomationConfiguration"]["stage"] == "LIVE"


def test_an_s3_uri_is_passed_through_unchanged() -> None:
    runtime = FakeRuntime()
    _client(runtime=runtime).extract("s3://other-bucket/contracts/x.pdf")
    assert runtime.calls[0]["inputConfiguration"]["s3Uri"] == "s3://other-bucket/contracts/x.pdf"


def test_polling_waits_until_success() -> None:
    runtime = FakeRuntime(states=["Created", "InProgress", "Success"])
    fields = _client(runtime=runtime).extract("contracts/ctr-001-v1.pdf")
    assert fields.customer_name == "Calder Logistics"


def test_a_service_error_is_raised_not_swallowed() -> None:
    runtime = FakeRuntime(states=["ServiceError"])
    with pytest.raises(DataAutomationError):
        _client(runtime=runtime).extract("contracts/ctr-001-v1.pdf")


def test_timeout_raises_instead_of_hanging() -> None:
    class NeverDone(FakeRuntime):
        def get_data_automation_status(self, invocationArn: str) -> dict:
            return {"status": "InProgress"}

    client = BedrockDataAutomation(
        project_arn=PROJECT,
        output_bucket="raw-bucket",
        poll_seconds=0,
        max_wait_seconds=0,
        client=NeverDone(),
        s3_client=FakeS3(),
    )
    with pytest.raises(DataAutomationError):
        client.extract("contracts/x.pdf")


def test_annex_b_fields_are_typed_from_the_result() -> None:
    fields = _client().extract("contracts/ctr-001-v1.pdf")
    assert fields.monthly_subscription == 4000
    assert fields.included_hours_per_month == 50
    assert "Supervision 24/7" in fields.services_included
    assert fields.exclusions == ("les développements applicatifs",)


def test_source_spans_are_kept_for_the_portal() -> None:
    """EF-CTR-02: each field must be shown next to the passage it came from."""
    fields = _client().extract("contracts/ctr-001-v1.pdf")
    assert fields.spans
    assert any(span.page == 1 for span in fields.spans.values())


def test_missing_result_json_is_an_explicit_error() -> None:
    s3 = FakeS3(keys=[])
    with pytest.raises(DataAutomationError):
        _client(s3=s3).extract("contracts/x.pdf")


def test_bare_key_without_bucket_is_refused() -> None:
    client = BedrockDataAutomation(project_arn=PROJECT, client=FakeRuntime(), s3_client=FakeS3())
    with pytest.raises(DataAutomationError):
        client.extract("contracts/x.pdf")


def test_boto3_is_only_imported_inside_methods() -> None:
    """The CI workers have no boto3: every import must be indented."""
    import sys
    from pathlib import Path

    module = sys.modules["marge.contracts.data_automation"]
    source = Path(module.__file__).read_text(encoding="utf-8")
    imports = [line for line in source.splitlines() if line.strip().startswith("import boto3")]
    assert imports, "the client must import boto3 somewhere"
    for line in imports:
        assert line.startswith("    "), f"top-level boto3 import: {line!r}"


def test_flat_result_shape_is_also_accepted() -> None:
    """Some envelopes answer without the analysis wrapper."""
    s3 = FakeS3(payload={"CUSTOMER_NAME": {"value": "Leroy"}, "MONTHLY_SUBSCRIPTION": {"value": "1200"}})
    fields = _client(s3=s3).extract("contracts/x.pdf")
    assert fields.customer_name == "Leroy"
    assert fields.monthly_subscription == 1200
