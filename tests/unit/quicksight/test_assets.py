"""The asset bundle: shape, determinism and deployment plan (offline)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from marge.quicksight import (
    AGENT,
    DASHBOARDS,
    DATASETS,
    FLOWS,
    RLS_RULES,
    SCENARIOS,
    TOPIC,
    bundle_json,
    to_asset_bundle,
)
from marge.quicksight.assets import ACCOUNT_NAME, BUNDLE_VERSION, write_bundle
from marge.quicksight.deploy import MANUAL_ACTIONS, build_plan, write_plan

BUNDLE_KEYS = (
    "bundle_version",
    "generated_by",
    "account",
    "datasets",
    "topic",
    "dashboards",
    "rls_rules",
    "scenarios",
    "agent",
    "flows",
)


def test_bundle_holds_the_expected_sections() -> None:
    bundle = to_asset_bundle()
    assert set(bundle) == set(BUNDLE_KEYS)


def test_bundle_metadata_names_the_account_and_the_region() -> None:
    account = to_asset_bundle()["account"]
    assert account["name"] == ACCOUNT_NAME
    assert account["region"]
    assert account["language"] == "en"


def test_bundle_carries_every_asset() -> None:
    bundle = to_asset_bundle()
    assert len(bundle["datasets"]) == len(DATASETS)
    assert len(bundle["dashboards"]) == len(DASHBOARDS)
    assert len(bundle["rls_rules"]) == len(RLS_RULES)
    assert len(bundle["scenarios"]) == len(SCENARIOS)
    assert bundle["agent"]["agent_id"] == AGENT.agent_id
    assert len(bundle["flows"]) == len(FLOWS)
    assert bundle["topic"]["name"] == TOPIC.name


def test_bundle_is_json_serialisable() -> None:
    payload = json.loads(bundle_json())
    assert payload["bundle_version"] == BUNDLE_VERSION


def test_bundle_serialisation_is_deterministic() -> None:
    assert bundle_json() == bundle_json()


def test_bundle_has_no_timestamp() -> None:
    """Two runs must give the same file: no timestamp, no random identifier."""
    raw = bundle_json().lower()
    for marker in ("generated_at", "timestamp", "created_at", "uuid"):
        assert marker not in raw


def test_bundle_json_is_sorted() -> None:
    raw = bundle_json()
    assert raw.startswith('{\n  "account"')


def test_write_bundle_produces_a_stable_file(tmp_path: Path) -> None:
    first = write_bundle(tmp_path)
    content = first.read_text(encoding="utf-8")
    write_bundle(tmp_path)
    assert first.read_text(encoding="utf-8") == content
    assert json.loads(content)["bundle_version"] == BUNDLE_VERSION


def test_committed_bundle_matches_the_code() -> None:
    """The committed bundle must be the one the code produces today."""
    committed = Path("infra/quicksight-assets/marge-assets.json")
    if not committed.exists():
        pytest.skip("bundle not generated yet")
    assert committed.read_text(encoding="utf-8") == bundle_json()


def test_deploy_plan_lists_the_programmable_steps() -> None:
    plan = build_plan()
    actions = {step["action"] for step in plan["programmable_steps"]}
    assert "create_data_source" in actions
    assert "create_dataset" in actions
    assert "create_topic" in actions
    assert "create_dashboard" in actions
    assert "apply_rls" in actions


def test_deploy_plan_covers_the_five_datasets_and_six_dashboards() -> None:
    plan = build_plan()
    resources = [step["resource"] for step in plan["programmable_steps"]]
    for dataset in DATASETS:
        assert f"quicksight_dataset:{dataset.name}" in resources
    for dashboard in DASHBOARDS:
        assert f"quicksight_dashboard:{dashboard.dashboard_id}" in resources


def test_deploy_plan_is_ordered() -> None:
    orders = [step["order"] for step in build_plan()["programmable_steps"]]
    assert orders == sorted(orders)


def test_deploy_plan_lists_the_manual_actions() -> None:
    plan = build_plan()
    ids = {action["action_id"] for action in plan["manual_actions"]}
    assert "MA-AGENT" in ids
    assert "MA-FLOW" in ids
    assert "MA-SPACE" in ids
    for action in plan["manual_actions"]:
        assert action["steps"]
        assert action["reference"]


def test_manual_actions_are_the_ones_of_chapter_22() -> None:
    ids = {action.action_id for action in MANUAL_ACTIONS}
    assert {"MA-AGENT", "MA-FLOW", "MA-SPACE"} <= ids


def test_write_plan_is_deterministic(tmp_path: Path) -> None:
    first = write_plan(tmp_path)
    content = first.read_text(encoding="utf-8")
    write_plan(tmp_path)
    assert first.read_text(encoding="utf-8") == content
    assert json.loads(content)["programmable_steps"]


def test_deploy_does_not_import_boto3_at_module_level() -> None:
    """docs/CONTRACT.md rule 4: boto3 is imported inside the functions."""
    for path in (
        Path("src/marge/quicksight/deploy.py"),
        Path("src/marge/quicksight/quick_api.py"),
    ):
        source = path.read_text(encoding="utf-8")
        module_level = [line for line in source.splitlines() if line.startswith("import boto3")]
        assert not module_level, path
    api_source = Path("src/marge/quicksight/quick_api.py").read_text(encoding="utf-8")
    assert "import boto3" in api_source


def test_deploy_dry_run_writes_a_plan_without_aws(tmp_path: Path) -> None:
    from marge.quicksight.deploy import main

    assert main(["--dry-run", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "deploy-plan.json").exists()
