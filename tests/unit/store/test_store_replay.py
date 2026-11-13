"""Regression tests: the store keys are natural keys, so a load can be replayed.

The deployed table received twice as many AWS cost rows as the dataset holds:
the key of a cost row carried the position of the row in the batch, so a
replay with another order wrote new rows beside the old ones and the costs
were counted twice.
"""

from __future__ import annotations

from decimal import Decimal

from tests.fakes.builders import golden_aws_costs, golden_tooling
from tests.unit.store.test_dynamo_store import FakeDynamoClient

from marge.domain import Month
from marge.store import DynamoStore, SqliteStore


def test_replaying_the_costs_does_not_duplicate_them(tmp_path) -> None:
    store = SqliteStore(tmp_path / "marge.sqlite3")
    try:
        store.save_tooling_costs(list(golden_tooling()))
        store.save_aws_costs(list(golden_aws_costs()))
        first_tooling = len(store.list_tooling_costs())
        first_costs = len(store.list_aws_costs())

        # The same rows, in another order.
        store.save_tooling_costs(list(reversed(list(golden_tooling()))))
        store.save_aws_costs(list(reversed(list(golden_aws_costs()))))

        assert len(store.list_tooling_costs()) == first_tooling
        assert len(store.list_aws_costs()) == first_costs
    finally:
        store.close()


def test_replaying_the_costs_does_not_duplicate_them_in_dynamodb() -> None:
    """Same guarantee on the deployed store: the key is the grain, not the position."""
    store = DynamoStore(client=FakeDynamoClient())
    store.save_tooling_costs(list(golden_tooling()))
    store.save_aws_costs(list(golden_aws_costs()))
    first_tooling = len(store.list_tooling_costs())
    first_costs = len(store.list_aws_costs())

    store.save_tooling_costs(list(reversed(list(golden_tooling()))))
    store.save_aws_costs(list(reversed(list(golden_aws_costs()))))

    assert len(store.list_tooling_costs()) == first_tooling
    assert len(store.list_aws_costs()) == first_costs


def test_the_costs_are_keyed_by_their_own_grain(tmp_path) -> None:
    store = SqliteStore(tmp_path / "marge.sqlite3")
    try:
        store.save_tooling_costs(list(golden_tooling()))
        store.save_aws_costs(list(golden_aws_costs()))
        tooling_keys = {cost.tool for cost in store.list_tooling_costs()}
        cost_keys = {(c.aws_account_id, str(c.month)) for c in store.list_aws_costs()}
        assert len(store.list_tooling_costs()) == len(tooling_keys)
        assert len(store.list_aws_costs()) == len(cost_keys)
        month = Month.parse("2026-10")
        assert store.list_aws_costs(month=month)
        assert all(c.month == month for c in store.list_aws_costs(month=month))
        assert all(c.cost == Decimal(c.cost) for c in store.list_aws_costs())
    finally:
        store.close()
