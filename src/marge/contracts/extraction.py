"""Reading Annex B fields out of a contract (EF-CTR-01, EF-CTR-02).

Two engines behind one interface:

* ``BedrockDataAutomation`` — the real one, boto3 imported inside the method,
  a custom field plan and source spans returned by the service (spec 13.1);
* ``LocalTextExtractor`` — deterministic, standard library only, used by the
  tests and by the offline demo. It finds each field in the contract text and
  keeps the passage it came from, so the portal can show value next to quote.

Nothing here decides whether a contract is valid: that is a human step
(``marge.contracts.validation``).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from ..domain import ContractFields, ExtractedField, SourceSpan
from .schema import parse_date, parse_list, parse_money, to_contract_fields

MONEY_RE = r"([0-9][0-9 \u00a0.,]*)"


@dataclass(slots=True)
class LocalTextExtractor:
    """Deterministic extractor: reads the contract prose, keeps the quotes."""

    def extract(self, document_key: str, content: bytes) -> ContractFields:
        text = content.decode("utf-8", errors="replace")
        payload, spans = self._read(text)
        fields = to_contract_fields(payload)
        fields.spans = spans
        return fields

    def _read(self, text: str) -> tuple[dict, dict[str, SourceSpan]]:
        lines = text.splitlines()
        payload: dict = {"currency": "EUR"}
        spans: dict[str, SourceSpan] = {}

        def grab(name: str, pattern: str, group: int = 1) -> str | None:
            for index, line in enumerate(lines):
                found = re.search(pattern, line, re.IGNORECASE)
                if found:
                    value = found.group(group).strip()
                    payload[name] = value
                    spans[name] = SourceSpan(quote=line.strip(), page=index // 40 + 1)
                    return value
            return None

        grab("customer_name", r"client\s*:\s*(.+)$")
        grab("start_date", r"(?:date d'effet|prise d'effet)\s*:\s*([^\n]+)")
        grab("end_date", r"(?:date de fin|échéance)\s*:\s*([^\n]+)")
        grab("renewal_terms", r"(?:reconduction)\s*:\s*([^\n]+)")
        grab("termination_notice", r"(?:préavis)\s*:\s*([^\n]+)")
        grab("monthly_subscription", r"(?:abonnement mensuel)\s*:\s*" + MONEY_RE)
        grab("included_hours_per_month", r"(?:heures incluses)\s*:\s*([0-9][0-9.,]*)")
        grab("extra_hour_rate", r"(?:tarif horaire hors forfait)\s*:\s*" + MONEY_RE)
        grab("service_hours", r"(?:plages? de service|horaires? de service)\s*:\s*([^\n]+)")
        grab("penalties", r"(?:pénalités?)\s*:\s*([^\n]+)")
        grab("indexation_clause", r"(?:indexation)\s*:\s*([^\n]+)")
        grab("covered_accounts_or_resources", r"(?:ressources? couvertes?)\s*:\s*([0-9]+)")

        payload["services_included"] = parse_list(self._block(text, "services inclus", "exclusions"))
        payload["exclusions"] = parse_list(self._block(text, "exclusions", "engagements"))
        included = ", ".join(payload["services_included"][:2])
        excluded = ", ".join(payload["exclusions"][:2])
        spans["services_included"] = SourceSpan(quote=f"Services inclus: {included}")
        spans["exclusions"] = SourceSpan(quote=f"Exclusions: {excluded}")
        payload["sla_commitments"] = [
            {"subject": line.strip(), "target": "", "penalty_rule": ""}
            for line in self._block(text, "engagements", "pénalités").splitlines()
            if line.strip()
        ]
        return payload, spans

    @staticmethod
    def _block(text: str, start: str, end: str) -> str:
        pattern = rf"{start}[^\n]*\n(.*?)(?:\n\s*{end}|$)"
        found = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        return found.group(1) if found else ""


class BedrockDataAutomation:
    """Contract extraction through Bedrock Data Automation (boto3, lazy)."""

    def __init__(self, profile_id: str = "marge-contract-fields-v1", client=None) -> None:
        self.profile_id = profile_id
        self._client = client

    def _runtime(self):
        if self._client is None:
            import boto3

            self._client = boto3.client("bedrock-data-automation-runtime")
        return self._client

    def extract(self, document_key: str, content: bytes) -> ContractFields:
        """Invoke the data automation job and map its output to Annex B."""
        from .schema import field_plan_payload

        response = self._runtime().invoke_data_automation_async(
            inputConfiguration={"s3Uri": document_key},
            outputConfiguration={"s3Uri": document_key + ".json"},
            dataAutomationConfiguration={"dataAutomationProjectArn": self.profile_id},
            dataAutomationProfileArn=self.profile_id,
        )
        raw = response.get("outputJson", "{}")
        payload = json.loads(raw) if isinstance(raw, str) else raw
        fields = to_contract_fields(payload)
        fields.spans = self._spans(payload)
        _ = field_plan_payload()  # the plan is what the project holds
        return fields

    @staticmethod
    def _spans(payload: dict) -> dict[str, SourceSpan]:
        spans: dict[str, SourceSpan] = {}
        for name, value in (payload.get("fieldLocations") or {}).items():
            spans[name] = SourceSpan(
                quote=str(value.get("quote", "")),
                page=value.get("page"),
                char_start=value.get("start"),
                char_end=value.get("end"),
            )
        return spans


def extract_fields(content: bytes, document_key: str = "", extractor=None) -> ContractFields:
    """Extract Annex B fields, falling back to the local engine."""
    engine = extractor or LocalTextExtractor()
    return engine.extract(document_key, content)


def side_by_side(fields: ContractFields) -> list[ExtractedField]:
    """EF-CTR-02 — every extracted value next to the passage it came from."""
    rows: list[ExtractedField] = []
    for name, span in sorted(fields.spans.items()):
        value = getattr(fields, name, "")
        if isinstance(value, (tuple, list)):
            value = "; ".join(str(item) for item in value)
        rows.append(ExtractedField(name=name, value=str(value), span=span))
    return rows


__all__ = [
    "BedrockDataAutomation",
    "LocalTextExtractor",
    "extract_fields",
    "parse_date",
    "parse_money",
    "side_by_side",
]
