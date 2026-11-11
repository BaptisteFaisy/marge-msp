"""Identifier and value validation shared by the DDL and the SQL generation.

Split out so neither ``athena`` (schema) nor ``athena_sql`` (queries) imports
the other: a single source of truth for what may reach Athena, no cycle.
"""

from __future__ import annotations

import re

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.\-]{1,61}[a-z0-9]$")
_PREFIX_RE = re.compile(r"^[A-Za-z0-9_/\-]+$")
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


def validate_identifier(name: str, kind: str = "identifier") -> str:
    """Reject anything that is not a bare SQL identifier."""
    if not _IDENT_RE.fullmatch(name or ""):
        raise ValueError(f"invalid {kind}: {name!r}")
    return name


def validate_s3_location(bucket: str, prefix: str) -> str:
    """Build and validate an ``s3://bucket/prefix/`` location."""
    if not _BUCKET_RE.fullmatch(bucket):
        raise ValueError(f"invalid S3 bucket name: {bucket!r}")
    cleaned = prefix.strip("/")
    if cleaned and not _PREFIX_RE.fullmatch(cleaned):
        raise ValueError(f"invalid S3 prefix: {prefix!r}")
    return f"s3://{bucket}/{cleaned}/" if cleaned else f"s3://{bucket}/"


def validate_month(month: str) -> str:
    if not _MONTH_RE.fullmatch(month):
        raise ValueError(f"expected YYYY-MM month, got {month!r}")
    return month


def validate_client_id(client_id: str) -> str:
    if not _CLIENT_ID_RE.fullmatch(client_id):
        raise ValueError(f"invalid client_id: {client_id!r}")
    return client_id
