"""Replaceable source connectors (spec 7, EF-SRC-01..04).

Another MSP plugs its own tool by writing one adapter: the interfaces live in
``marge.ingest.base`` and nothing else imports a vendor SDK.
"""

from __future__ import annotations

from .base import (
    BillingSource,
    ContractSource,
    DocumentExtractor,
    InvoiceSource,
    ItsmActions,
    TicketSource,
    WorkClassifier,
)
from .billing import load_aws_costs, parse_fx
from .invoices import LocalContractSource, S3ContractSource, load_invoices
from .loaders import SourceFiles, load_month, load_reference_data
from .tickets import level_from, load_interventions, strip_personal_data

__all__ = [
    "BillingSource",
    "ContractSource",
    "DocumentExtractor",
    "InvoiceSource",
    "ItsmActions",
    "LocalContractSource",
    "S3ContractSource",
    "SourceFiles",
    "TicketSource",
    "WorkClassifier",
    "level_from",
    "load_aws_costs",
    "load_interventions",
    "load_invoices",
    "load_month",
    "load_reference_data",
    "parse_fx",
    "strip_personal_data",
]
