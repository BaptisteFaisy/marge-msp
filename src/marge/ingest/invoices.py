"""Invoice loading (EF-SRC-04, spec 12.1) and contract document sources."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from decimal import Decimal, InvalidOperation

from ..domain import Contract, ContractFields, ContractStatus, Invoice, InvoiceKind, Month, SourceKind
from ..match import MappingResolver


def _decimal(raw: str | None) -> Decimal:
    try:
        return Decimal((raw or "0").replace(",", ".").strip())
    except InvalidOperation:
        return Decimal("0")


def to_invoice(row: dict[str, str], resolver: MappingResolver) -> Invoice | None:
    """Build one ``Invoice``; returns ``None`` when the client is unknown."""
    client_id = resolver.resolve(SourceKind.INVOICE, (row.get("customer_ref") or "").strip())
    if not client_id:
        return None
    return Invoice(
        invoice_id=row["invoice_id"].strip(),
        client_id=client_id,
        month=Month.parse(row["month"]),
        kind=InvoiceKind((row.get("kind") or "EXTRA_HOURS").strip().upper()),
        amount=_decimal(row.get("amount")),
        hours_billed=_decimal(row.get("hours_billed")),
        currency=(row.get("currency") or "EUR").upper(),
    )


def load_invoices(rows: Iterable[dict[str, str]], resolver: MappingResolver) -> Iterator[Invoice]:
    """Turn invoice rows into ``Invoice`` objects, skipping unknown clients."""
    for row in rows:
        invoice = to_invoice(row, resolver)
        if invoice is not None:
            yield invoice


class LocalContractSource:
    """Contract documents read from a local directory (demo, tests)."""

    def __init__(self, root: str) -> None:
        from pathlib import Path

        self.root = Path(root)

    def list_documents(self) -> Sequence[str]:
        return sorted(str(p.relative_to(self.root)) for p in self.root.glob("*.pdf"))

    def read_document(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

    def fetch_contracts(self) -> Iterator[Contract]:
        for key in self.list_documents():
            yield Contract(
                contract_id=key.split("/")[-1].split("-v")[0],
                client_id="",
                version=1,
                fields=ContractFields(),
                status=ContractStatus.RECEIVED,
                document_key=key,
            )


class S3ContractSource:
    """Contract documents read from S3 (boto3 imported inside the methods)."""

    def __init__(self, bucket: str, prefix: str = "contracts/", client=None) -> None:
        self.bucket = bucket
        self.prefix = prefix
        self._client = client

    def _s3(self):
        if self._client is None:
            import boto3

            self._client = boto3.client("s3")
        return self._client

    def list_documents(self) -> Sequence[str]:
        response = self._s3().list_objects_v2(Bucket=self.bucket, Prefix=self.prefix)
        return sorted(item["Key"] for item in response.get("Contents", []))

    def read_document(self, key: str) -> bytes:
        return self._s3().get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def fetch_contracts(self) -> Iterator[Contract]:
        for key in self.list_documents():
            if not key.endswith(".pdf"):
                continue
            name = key.split("/")[-1]
            yield Contract(
                contract_id=name.split("-v")[0],
                client_id="",
                version=int(name.split("-v")[1].split(".")[0]) if "-v" in name else 1,
                fields=ContractFields(),
                status=ContractStatus.RECEIVED,
                document_key=key,
            )
