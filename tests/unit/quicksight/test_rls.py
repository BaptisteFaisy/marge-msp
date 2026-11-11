"""Row-level security: EF-TDB-06 and ENF-CONF-03."""

from __future__ import annotations

import pytest

from marge.quicksight import DASHBOARDS, DATASET_NAMES, RLS_RULE_IDS, RLS_RULES, rls_by_id

SCOPE_RULE = "RLS-ACCOUNT-MANAGER-SCOPE"
COST_RULE = "RLS-HOURLY-COST-RESTRICTED"

ALL_ROLES = (
    "EXECUTIVE",
    "OPERATIONS_DIRECTOR",
    "ACCOUNT_MANAGER",
    "CONTROLLER",
    "ADMINISTRATOR",
)


def test_two_rules_are_declared() -> None:
    assert len(RLS_RULES) == 2
    assert RLS_RULE_IDS == (SCOPE_RULE, COST_RULE)


def test_scope_rule_covers_the_five_datasets() -> None:
    rule = rls_by_id(SCOPE_RULE)
    assert set(rule.protected_datasets) == set(DATASET_NAMES)


@pytest.mark.parametrize("role", ALL_ROLES)
def test_scope_rule_covers_every_role(role: str) -> None:
    rule = rls_by_id(SCOPE_RULE)
    assert rule.values_for(role)


def test_account_manager_only_sees_its_own_clients() -> None:
    rule = rls_by_id(SCOPE_RULE)
    assert rule.values_for("ACCOUNT_MANAGER") == ("SELF",)
    for role in ("EXECUTIVE", "OPERATIONS_DIRECTOR", "CONTROLLER", "ADMINISTRATOR"):
        assert rule.values_for(role) == ("ALL",)


def test_hourly_cost_rule_protects_the_rates() -> None:
    """ENF-CONF-03: the hourly costs are readable by the controller and the direction."""
    rule = rls_by_id(COST_RULE)
    assert rule.values_for("CONTROLLER") == ("ALL",)
    assert rule.values_for("EXECUTIVE") == ("ALL",)
    assert rule.values_for("ACCOUNT_MANAGER") == ("NONE",)
    assert rule.values_for("OPERATIONS_DIRECTOR") == ("NONE",)


def test_hourly_cost_rule_names_the_protected_fields() -> None:
    rule = rls_by_id(COST_RULE)
    assert rule.protected_fields
    for field in rule.protected_fields:
        dataset_name, column = field.split(".")
        assert dataset_name in DATASET_NAMES
        assert column


def test_both_rules_use_the_same_identity_parameter() -> None:
    parameters = {rule.identity_parameter for rule in RLS_RULES}
    assert len(parameters) == 1
    assert rules_identity_source_is_documented()


def rules_identity_source_is_documented() -> bool:
    return all(rule.identity_source for rule in RLS_RULES)


def test_identity_parameter_names_the_account_manager() -> None:
    rule = rls_by_id(SCOPE_RULE)
    assert "account_manager" in rule.identity_parameter


def test_every_dataset_carries_the_account_manager_column() -> None:
    """The row filter needs account_manager_id on every filtered table."""
    from marge.quicksight import dataset_by_name

    for name in DATASET_NAMES:
        assert "account_manager_id" in dataset_by_name(name).field_names


def test_at_least_one_dashboard_applies_the_scope_rule() -> None:
    applied = [rule for dashboard in DASHBOARDS for rule in dashboard.row_filter_rules]
    assert applied.count(SCOPE_RULE) >= 1


def test_rls_unknown_rule_raises() -> None:
    with pytest.raises(KeyError):
        rls_by_id("RLS-NOPE")
