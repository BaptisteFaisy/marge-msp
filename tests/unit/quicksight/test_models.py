"""JSON serialisation of the asset dataclasses."""

from __future__ import annotations

import json
from decimal import Decimal

from marge.quicksight import DATASETS, TOPIC, to_jsonable
from marge.quicksight.models import FieldSpec


def test_to_jsonable_converts_a_dataclass() -> None:
    payload = to_jsonable(FieldSpec("margin", "decimal", "Revenue minus cost", unit="EUR"))
    assert payload == {
        "name": "margin",
        "data_type": "decimal",
        "description": "Revenue minus cost",
        "unit": "EUR",
        "sensitive": False,
    }


def test_to_jsonable_converts_a_tuple_of_dataclasses() -> None:
    payload = to_jsonable(DATASETS)
    assert isinstance(payload, list)
    assert payload[0]["name"] == "marge_client_mois"
    assert isinstance(payload[0]["fields"], list)


def test_to_jsonable_converts_a_decimal_to_a_string() -> None:
    assert to_jsonable(Decimal("19.37")) == "19.37"


def test_to_jsonable_converts_a_nested_structure() -> None:
    payload = to_jsonable({"topic": TOPIC})
    assert payload["topic"]["name"] == "marge_topic"
    assert isinstance(payload["topic"]["metrics"], list)


def test_every_dataclass_round_trips_through_json() -> None:
    payload = to_jsonable(DATASETS)
    restored = json.loads(json.dumps(payload))
    assert restored == payload


def test_topic_metrics_are_json_serialisable() -> None:
    payload = json.loads(json.dumps(to_jsonable(TOPIC)))
    names = [metric["name"] for metric in payload["metrics"]]
    assert "margin" in names
    assert payload["synonyms"]
