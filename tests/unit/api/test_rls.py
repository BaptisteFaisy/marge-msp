"""Pure row-level filtering functions (EF-TDB-06, ENF-CONF-03..04)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from marge.api.auth import Actor
from marge.api.rls import (
    REDACTED_RATE,
    can_access_client,
    filter_by_clients,
    redact_rates_for_actor,
    redact_row,
    row_filter,
    visible_client_ids,
)
from marge.domain import ActorRole, Client, Rate, WorkLevel

CLIENTS = (
    Client(client_id="c-001", name="Calder", account_manager_id="am-01"),
    Client(client_id="c-002", name="Dupont", account_manager_id="am-02"),
)
AM = Actor(actor_id="am-01", role=ActorRole.ACCOUNT_MANAGER)
CONTROLLER = Actor(actor_id="controller-01", role=ActorRole.CONTROLLER)
RATES = (Rate(level=WorkLevel.N2, hourly_cost=Decimal("70"), effective_from=date(2026, 1, 1)),)


def test_visible_client_ids_account_manager_sees_only_own_clients() -> None:
    assert visible_client_ids(AM, CLIENTS) == {"c-001"}


def test_visible_client_ids_controller_sees_all_clients() -> None:
    assert visible_client_ids(CONTROLLER, CLIENTS) == {"c-001", "c-002"}


def test_can_access_client_denies_other_account_manager_clients() -> None:
    assert can_access_client(AM, "c-001", CLIENTS) is True
    assert can_access_client(AM, "c-002", CLIENTS) is False


def test_row_filter_allows_management_without_client_id() -> None:
    assert row_filter(CONTROLLER, CLIENTS, None) is True


def test_row_filter_denies_account_manager_without_client_id() -> None:
    assert row_filter(AM, CLIENTS, None) is False


def test_filter_by_clients_keeps_only_visible_rows() -> None:
    rows = [{"client_id": "c-001"}, {"client_id": "c-002"}, {"client_id": "c-001"}]
    assert filter_by_clients(rows, AM, CLIENTS) == [{"client_id": "c-001"}, {"client_id": "c-001"}]


def test_redact_rates_hides_hourly_cost_from_account_manager() -> None:
    redacted = redact_rates_for_actor(RATES, AM)
    assert redacted[0]["hourly_cost"] == REDACTED_RATE
    assert redacted[0]["level"] == "N2"


def test_redact_rates_shows_hourly_cost_to_controller() -> None:
    redacted = redact_rates_for_actor(RATES, CONTROLLER)
    assert redacted[0]["hourly_cost"] == "70.00"


def test_redact_row_hides_labour_and_discount_keys_for_account_manager() -> None:
    row = {"labour_cost": "70.00", "internal_discount": "12%", "client_id": "c-001"}
    redacted = redact_row(row, AM)
    assert redacted["labour_cost"] == REDACTED_RATE
    assert redacted["internal_discount"] == REDACTED_RATE
    assert redacted["client_id"] == "c-001"


def test_redact_row_keeps_everything_for_executive() -> None:
    executive = Actor(actor_id="exec-01", role=ActorRole.EXECUTIVE)
    row = {"labour_cost": "70.00", "internal_discount": "12%"}
    assert redact_row(row, executive) == row
