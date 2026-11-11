"""Reading Annex B fields out of a contract (EF-CTR-01, EF-CTR-02).

Two engines behind one interface:

* ``BedrockDataAutomation`` — the real one, boto3 imported inside the method,
  a custom field plan and source spans returned by the service (spec 13.1);
* ``LocalTextExtractor`` — deterministic, standard library only, used by the
  tests, the offline demo and the evaluation harness. It reads the two
  layouts a real MSP uses (prose and a table of conditions) and keeps the
  passage each value came from, so the portal can show value next to quote.

Nothing here decides whether a contract is valid: that is a human step
(``marge.contracts.validation``).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from ..domain import ContractFields, ExtractedField, SourceSpan
from .schema import parse_date, parse_money, to_contract_fields

AMOUNT = r"([0-9][0-9 \u00a0.,]*)"

LABELS: dict[str, str] = {
    "client": "customer_name",
    "raison sociale": "customer_name",
    "date d'effet": "start_date",
    "date de début": "start_date",
    "prise d'effet": "start_date",
    "date de fin": "end_date",
    "échéance": "end_date",
    "reconduction": "renewal_terms",
    "préavis de résiliation": "termination_notice",
    "préavis": "termination_notice",
    "abonnement mensuel": "monthly_subscription",
    "devise": "currency",
    "heures incluses par mois": "included_hours_per_month",
    "heures incluses": "included_hours_per_month",
    "forfait mensuel": "included_hours_per_month",
    "tarif horaire hors forfait": "extra_hour_rate",
    "plages de service": "service_hours",
    "horaires de service": "service_hours",
    "pénalités": "penalties",
    "indexation": "indexation_clause",
    "clause d'indexation": "indexation_clause",
    "comptes et ressources couverts": "covered_accounts_or_resources",
    "ressources couvertes": "covered_accounts_or_resources",
}

NARRATIVE: dict[str, tuple[str, int]] = {
    "customer_name": (r"ci-après\s*«\s*le Client\s*»\s*,\s*([^,\n]{3,80})", 1),
    "start_date": (
        r"(?:prend effet|effet le|entré en vigueur le)\s+(?:le\s+)?([0-9]{1,2}\s+\w+\s+[0-9]{4})",
        1,
    ),
    "end_date": (r"(?:se termine|termine le)\s+(?:le\s+)?([0-9]{1,2}\s+\w+\s+[0-9]{4})", 1),
    "renewal_terms": (r"renouvelable\s+selon\s+les\s+modalités\s+suivantes\s*:\s*([^.\n]+)", 1),
    "termination_notice": (r"préavis de résiliation est de\s+([0-9]+\s*(?:mois|jours?|semaines?))", 1),
    "monthly_subscription": (
        r"(?:abonnement mensuel (?:est fixé à|de|fixé à)|prix de l'abonnement mensuel est fixé à)\s*"
        + AMOUNT,
        1,
    ),
    "included_hours_per_month": (
        r"(?:couvrant|comprend|pour)\s*" + AMOUNT + r"\s*heures?\s*(?:par mois|incluses chaque mois)",
        1,
    ),
    "extra_hour_rate": (
        r"(?:tarif horaire hors forfait (?:de|s'établit à)|facturée)\s*" + AMOUNT,
        1,
    ),
    "service_hours": (r"Plages? de service\s*:\s*([^\n]+)", 1),
    "penalties": (r"Pénalités?\s*:\s*([^\n]+)", 1),
    "indexation_clause": (r"Clause d'indexation\s*:\s*([^\n]+)", 1),
    "covered_accounts_or_resources": (r"couvre\s+([0-9]+)\s+comptes? ou ressources", 1),
}

LABEL_LINE = re.compile(r"^\s*(?P<label>[A-Za-zÀ-ÿ][^:\n]{2,45})\s*:\s*(?P<value>.+?)\s*$")

LIST_HEADINGS = {
    "services_included": ("services inclus", "services couverts"),
    "exclusions": ("exclusions",),
}

BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(?P<item>.+)$")


@dataclass(slots=True)
class LocalTextExtractor:
    """Deterministic extractor: reads the contract, keeps the quotes."""

    def extract(self, document_key: str, content: bytes) -> ContractFields:
        text = content.decode("utf-8", errors="replace")
        pairs, spans = self._pairs(text)
        payload = self._payload(text, pairs)
        fields = to_contract_fields(payload)
        fields.spans = spans
        return fields

    # ------------------------------------------------------------- parsing
    def _pairs(self, text: str) -> tuple[dict[str, str], dict[str, SourceSpan]]:
        pairs: dict[str, str] = {}
        spans: dict[str, SourceSpan] = {}
        for label, value, quote, page in self._table_rows(text):
            field = LABELS.get(label.lower().strip())
            if field and field not in pairs:
                pairs[field] = value
                spans[field] = SourceSpan(quote=quote, page=page)
        for label, value, quote in self._label_lines(text):
            field = LABELS.get(label.lower().strip())
            if field and field not in pairs:
                pairs[field] = value
                spans[field] = SourceSpan(quote=quote)
        for field, (pattern, group) in NARRATIVE.items():
            if field in pairs:
                continue
            found = re.search(pattern, text, re.IGNORECASE)
            if found:
                pairs[field] = found.group(group).strip()
                spans[field] = SourceSpan(quote=found.group(0).strip()[:300])
        if "customer_name" not in pairs:
            name = self._title_name(text)
            if name:
                pairs["customer_name"] = name
                spans["customer_name"] = SourceSpan(quote=name)
        return pairs, spans

    @staticmethod
    def _table_rows(text: str) -> list[tuple[str, str, str, int]]:
        rows: list[tuple[str, str, str, int]] = []
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if "|" not in line:
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 2 or cells[0].lower() in ("champ", "libellé", "critère"):
                continue
            rows.append((cells[0], cells[1], line.strip(), index // 40 + 1))
        return rows

    @staticmethod
    def _label_lines(text: str) -> list[tuple[str, str, str]]:
        """``Label : value`` lines, the second layout a real MSP uses."""
        rows: list[tuple[str, str, str]] = []
        for line in text.splitlines():
            found = LABEL_LINE.match(line)
            if found:
                rows.append((found.group("label"), found.group("value"), line.strip()))
        return rows

    @staticmethod
    def _title_name(text: str) -> str:
        for line in text.splitlines()[:6]:
            if " — " in line:
                candidate = line.split(" — ", 1)[1].strip()
                if candidate and not candidate.lower().startswith("version"):
                    return candidate
        return ""

    def _payload(self, text: str, pairs: dict[str, str]) -> dict:
        payload = dict(pairs)
        payload.setdefault("currency", "EUR")
        for name in LIST_HEADINGS:
            items = self._list_items(text, name)
            if items:
                payload[name] = items
        return payload

    @staticmethod
    def _heading_index(lines: list[str], headings: tuple[str, ...]) -> int:
        for index, line in enumerate(lines):
            lowered = line.lower()
            if any(heading in lowered for heading in headings):
                return index
        return -1

    def _list_items(self, text: str, name: str) -> list[str]:
        """The items of a section, in reading order, from prose or from a table."""
        lines = text.splitlines()
        headings = LIST_HEADINGS[name]
        start = self._heading_index(lines, headings)
        if start < 0:
            return []
        heading_line = lines[start]
        if "|" in heading_line:
            return self._table_items(lines, start)
        return self._prose_items(lines, start)

    @staticmethod
    def _table_items(lines: list[str], start: int) -> list[str]:
        items: list[str] = []
        for line in lines[start + 1 :]:
            if "|" not in line:
                if items:
                    break
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if not cells[0] and len(cells) > 1 and cells[1]:
                items.append(cells[1])
                continue
            break
        return items

    @staticmethod
    def _prose_items(lines: list[str], start: int) -> list[str]:
        items: list[str] = []
        for line in lines[start + 1 :]:
            stripped = line.strip()
            if stripped.lower().startswith("article "):
                break
            bullet = BULLET.match(line)
            if bullet:
                items.append(bullet.group("item").strip())
                continue
            if stripped and not items and ":" in stripped:
                label, _, rest = stripped.partition(":")
                if any(heading in label.lower() for heading in ("inclus", "exclu")):
                    items.extend(part.strip() for part in rest.split(",") if part.strip())
                    continue
            if stripped and items:
                break
        return items


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
