"""Serialisation of domain objects to and from JSON-compatible dicts.

One implementation shared by the SQLite store, the DynamoDB store and the API
serialisers: no persistence layer ever builds its own mapping (that would be
the same logic written four times).

Money is always a string so no float ever touches an amount.
"""

from __future__ import annotations

import dataclasses
import enum
import types
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Union, get_args, get_origin, get_type_hints

SCALARS = (str, int, float, bool, Decimal, date, datetime)


def encode(value: Any) -> Any:
    """Turn a domain value into something ``json.dumps`` accepts."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return value.value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: encode(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k): encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [encode(v) for v in value]
    return value


def decode_scalar(raw: Any, kind: Any) -> Any:
    """Decode one scalar field according to its declared type."""
    if raw is None:
        return None
    if kind is Decimal:
        return Decimal(str(raw))
    if kind is date:
        return date.fromisoformat(str(raw))
    if kind is datetime:
        return datetime.fromisoformat(str(raw))
    if isinstance(kind, type) and issubclass(kind, enum.Enum):
        return kind(raw)
    if kind is int:
        return int(raw)
    if kind is float:
        return float(raw)
    if kind is bool:
        return bool(raw)
    return raw


def _unwrap_optional(kind: Any) -> Any:
    """``X | None`` and ``Optional[X]`` both become ``X``."""
    origin = get_origin(kind)
    if origin in (Union, types.UnionType):
        args = [a for a in get_args(kind) if a is not type(None)]
        return args[0] if args else Any
    return kind


def _decode_container(raw: Any, kind: Any) -> Any:
    origin = get_origin(kind)
    args = get_args(kind)
    inner = _unwrap_optional(args[0]) if args else Any
    if origin is dict:
        return {str(k): v for k, v in (raw or {}).items()}
    items = raw or []
    if dataclasses.is_dataclass(inner) and isinstance(inner, type):
        return [decode(inner, item) for item in items]
    return [decode_scalar(item, inner) for item in items]


def decode(cls: type, payload: dict[str, Any]) -> Any:
    """Rebuild a domain dataclass from its JSON dict."""
    hints = get_type_hints(cls)
    kwargs: dict[str, Any] = {}
    for field in dataclasses.fields(cls):
        if field.name not in payload:
            continue
        raw = payload[field.name]
        kind = _unwrap_optional(hints.get(field.name, Any))
        origin = get_origin(kind)
        if origin in (tuple, list, dict):
            value = _decode_container(raw, kind)
            kwargs[field.name] = tuple(value) if origin is tuple else value
        elif dataclasses.is_dataclass(kind) and isinstance(kind, type):
            kwargs[field.name] = decode(kind, raw) if isinstance(raw, dict) else None
        elif kind in SCALARS or (isinstance(kind, type) and issubclass(kind, enum.Enum)):
            kwargs[field.name] = decode_scalar(raw, kind)
        else:
            kwargs[field.name] = raw
    return cls(**kwargs)


def decode_many(cls: type, payloads: list[dict[str, Any]]) -> list[Any]:
    """Decode a list of rows."""
    return [decode(cls, item) for item in payloads]
