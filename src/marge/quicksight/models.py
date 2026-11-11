"""Shared dataclasses for the Quick (Quick Sight) asset layer.

Everything here is a plain, frozen dataclass: standard library only, JSON
serialisable, no third-party dependency (docs/CONTRACT.md rules 3 and 4).

``marge.quicksight`` owns these types. The domain and calculation layers are
never imported from here: they stay the single source of truth for every
figure (ENF-IA-01).
"""

from __future__ import annotations

from dataclasses import dataclass, is_dataclass
from dataclasses import fields as dataclass_fields
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

__all__ = [
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
    "to_jsonable",
]


def to_jsonable(value: Any) -> Any:
    """Convert dataclasses, tuples, decimals and dates into JSON values."""
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in dataclass_fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (tuple, list)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    return value


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """One column of an analytical table (Annex A)."""

    name: str
    data_type: str
    description: str
    unit: str = ""
    sensitive: bool = False


@dataclass(frozen=True, slots=True)
class DatasetSpec:
    """One Quick Sight dataset: grain, fields, keys and the Athena query."""

    name: str
    grain: str
    fields: tuple[FieldSpec, ...]
    keys: tuple[str, ...]
    sql: str
    description: str
    requirement: str = ""
    refresh: str = "nightly"

    @property
    def field_names(self) -> tuple[str, ...]:
        """Names of the columns, in declaration order."""
        return tuple(f.name for f in self.fields)

    def field(self, name: str) -> FieldSpec:
        """Return the column ``name`` or raise ``KeyError``."""
        for spec in self.fields:
            if spec.name == name:
                return spec
        raise KeyError(f"{self.name} has no field {name!r}")


@dataclass(frozen=True, slots=True)
class SynonymSpec:
    """A business word mapped onto a metric of the topic (spec 14.1)."""

    term: str
    metric: str
    note: str = ""


@dataclass(frozen=True, slots=True)
class MetricSpec:
    """One business metric of the semantic layer (spec 14.1, spec 12)."""

    name: str
    label: str
    definition: str
    formula: str
    unit: str
    default_aggregation: str
    source_dataset: str
    source_fields: tuple[str, ...]
    synonyms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class JoinSpec:
    """A join between two datasets of the topic."""

    left: str
    right: str
    on: tuple[str, ...]
    cardinality: str
    purpose: str


@dataclass(frozen=True, slots=True)
class TopicSpec:
    """The Quick Sight topic: the semantic layer of the project (spec 14.1)."""

    name: str
    description: str
    metrics: tuple[MetricSpec, ...]
    synonyms: tuple[SynonymSpec, ...]
    joins: tuple[JoinSpec, ...]
    datasets: tuple[str, ...]
    default_aggregations: tuple[str, ...] = ()
    requirement: str = ""

    def metric(self, name: str) -> MetricSpec:
        """Return the metric ``name`` or raise ``KeyError``."""
        for metric in self.metrics:
            if metric.name == name:
                return metric
        raise KeyError(f"no metric named {name!r}")


@dataclass(frozen=True, slots=True)
class WidgetSpec:
    """One visual of a dashboard."""

    name: str
    widget_type: str
    title: str
    dataset: str
    fields: tuple[str, ...]
    measures: tuple[str, ...] = ()
    filters: tuple[str, ...] = ()
    group_by: tuple[str, ...] = ()
    sort_by: str = ""
    description: str = ""


@dataclass(frozen=True, slots=True)
class DashboardSpec:
    """One Quick Sight dashboard (EF-TDB-01..06)."""

    dashboard_id: str
    title: str
    requirement: str
    description: str
    datasets: tuple[str, ...]
    widgets: tuple[WidgetSpec, ...]
    row_filter_rules: tuple[str, ...]
    owner_role: str
    default_filters: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RlsRule:
    """A row-level security rule (EF-TDB-06, ENF-CONF-03)."""

    rule_id: str
    identity_parameter: str
    identity_source: str
    role_values: tuple[tuple[str, tuple[str, ...]], ...]
    protected_datasets: tuple[str, ...]
    protected_fields: tuple[str, ...]
    description: str
    requirement: str = ""

    def values_for(self, role: str) -> tuple[str, ...]:
        """Allowed values of the identity parameter for ``role``."""
        for known_role, values in self.role_values:
            if known_role == role:
                return values
        return ()


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    """One tunable parameter of a scenario."""

    name: str
    data_type: str
    default: str
    minimum: str
    maximum: str
    unit: str
    description: str


@dataclass(frozen=True, slots=True)
class ScenarioSpec:
    """A simulation: parameters and a formula evaluated by the server."""

    scenario_id: str
    title: str
    requirement: str
    description: str
    parameters: tuple[ParameterSpec, ...]
    formula: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    computed_by: str
    note: str = ""


@dataclass(frozen=True, slots=True)
class AgentExample:
    """One reference question with the shape of its expected answer."""

    example_id: str
    question: str
    expected_answer: str
    dashboard: str
    must_cite: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """The chat agent: instructions, knowledge and actions (EF-AGT-01..03)."""

    agent_id: str
    name: str
    description: str
    instructions: tuple[str, ...]
    knowledge: tuple[str, ...]
    actions: tuple[str, ...]
    examples: tuple[AgentExample, ...]
    language: str
    rules: tuple[str, ...] = ()
    requirement: str = ""


@dataclass(frozen=True, slots=True)
class FlowStep:
    """One step of the scheduled review flow."""

    order: int
    action: str
    detail: str


@dataclass(frozen=True, slots=True)
class FlowSpec:
    """The scheduled monthly review flow (EF-REV-01..03)."""

    flow_id: str
    name: str
    requirement: str
    owner: str
    schedule: str
    sources: tuple[str, ...]
    destinations: tuple[str, ...]
    steps: tuple[FlowStep, ...]
    fallback: str
    template: str
    description: str = ""
