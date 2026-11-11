"""Quick (Quick Sight) assets of Marge: datasets, topic, dashboards, RLS, scenarios.

The public API is the one of docs/CONTRACT.md section 3:

``DATASETS``, ``TOPIC``, ``DASHBOARDS``, ``RLS_RULES``, ``SCENARIOS``,
``AGENT``, ``FLOWS`` and ``to_asset_bundle``.

Standard library only: ``boto3`` is imported inside the functions of
``deploy`` that call AWS, so the test suite never needs it.
"""

from __future__ import annotations

from .agent import AGENT
from .assets import ACCOUNT_NAME, BUNDLE_VERSION, DEFAULT_REGION, bundle_json, to_asset_bundle
from .dashboards import DASHBOARD_IDS, DASHBOARDS, dashboard_by_id
from .datasets import DATASET_NAMES, DATASETS, dataset_by_name
from .flows import FLOW_IDS, FLOWS, flow_by_id
from .models import (
    AgentExample,
    AgentSpec,
    DashboardSpec,
    DatasetSpec,
    FieldSpec,
    FlowSpec,
    FlowStep,
    JoinSpec,
    MetricSpec,
    ParameterSpec,
    RlsRule,
    ScenarioSpec,
    SynonymSpec,
    TopicSpec,
    WidgetSpec,
    to_jsonable,
)
from .rls import RLS_RULE_IDS, RLS_RULES, rls_by_id
from .scenarios import SCENARIO_IDS, SCENARIOS, scenario_by_id
from .topic import MARGIN_SYNONYMS, TOPIC

__all__ = [
    "ACCOUNT_NAME",
    "AGENT",
    "BUNDLE_VERSION",
    "DASHBOARDS",
    "DASHBOARD_IDS",
    "DATASETS",
    "DATASET_NAMES",
    "DEFAULT_REGION",
    "FLOWS",
    "FLOW_IDS",
    "MARGIN_SYNONYMS",
    "RLS_RULES",
    "RLS_RULE_IDS",
    "SCENARIOS",
    "SCENARIO_IDS",
    "TOPIC",
    "AgentExample",
    "AgentSpec",
    "DashboardSpec",
    "DatasetSpec",
    "FieldSpec",
    "FlowSpec",
    "FlowStep",
    "JoinSpec",
    "MetricSpec",
    "ParameterSpec",
    "RlsRule",
    "ScenarioSpec",
    "SynonymSpec",
    "TopicSpec",
    "WidgetSpec",
    "bundle_json",
    "dashboard_by_id",
    "dataset_by_name",
    "flow_by_id",
    "rls_by_id",
    "scenario_by_id",
    "to_asset_bundle",
    "to_jsonable",
]
