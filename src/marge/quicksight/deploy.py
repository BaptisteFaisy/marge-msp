"""Deployment of the Quick assets to AWS (spec 11.2, risk of chapter 22).

``boto3`` is imported inside the functions that call AWS, so the test suite
never needs it (docs/CONTRACT.md rule 4).

Two parts:

* the programmable part — data source, datasets, topic, dashboards and the
  row-level rules, created through the Quick Sight API (see
  ``marge.quicksight.quick_api``);
* the manual part — the chat agent, the scheduled flow and the project space
  keep a step-by-step procedure here and in the README: their console
  configuration (knowledge base, MCP tools, ownership, memberships) is not
  reproducible by program, which is the risk rated in chapter 22 of the
  specification.

``python -m marge.quicksight.deploy --dry-run`` writes the plan without
calling AWS.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import quick_api
from .assets import ACCOUNT_NAME, DEFAULT_REGION, to_asset_bundle
from .models import to_jsonable

__all__ = [
    "MANUAL_ACTIONS",
    "DeployStep",
    "ManualAction",
    "build_plan",
    "deploy",
    "main",
    "write_plan",
]

DEFAULT_PLAN_NAME = "deploy-plan.json"


@dataclass(frozen=True, slots=True)
class DeployStep:
    """One API call of the deployment plan."""

    order: int
    action: str
    resource: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    api: str = ""


@dataclass(frozen=True, slots=True)
class ManualAction:
    """An asset that has to be created by hand, with its steps."""

    action_id: str
    resource: str
    description: str
    steps: tuple[str, ...]
    reference: str = ""


MANUAL_ACTIONS: tuple[ManualAction, ...] = (
    ManualAction(
        action_id="MA-AGENT",
        resource="Chat agent (EF-AGT-01..03)",
        description=(
            "The agent API exists (CreateAgent) but the deployment keeps it manual: the agent "
            "must be bound to the topic, the contracts space and the three MCP tools in the "
            "console, and it needs a Professional licence per account manager. Chapter 22 rates "
            "this risk as 'strong probability, low impact'."
        ),
        steps=(
            "Open the Quick console, then Agents, then Create agent.",
            "Name it 'Profitability analyst' and paste the instructions of the agent section of "
            "the bundle (agent.instructions and agent.rules).",
            "Attach the knowledge: the topic marge_topic and the contracts space marge_project.",
            "Attach the three MCP actions create_renegotiation_task, "
            "draft_extra_billing_proposal and get_margin_breakdown.",
            "Add the five reference questions of agent.examples as the test set of the agent.",
            "Publish the agent and give it the Professional licence of the account managers.",
        ),
        reference="docs/SPEC.fr.md chapter 22, risk 'Agents, flows and spaces are not creatable by program'",
    ),
    ManualAction(
        action_id="MA-FLOW",
        resource="Scheduled flow (EF-REV-01, EF-REV-02)",
        description=(
            "A scheduled flow belongs to the user who creates it (spec 14.4), so it is created by "
            "the controller in the console. The flow API (CreateFlow) cannot transfer ownership."
        ),
        steps=(
            "Sign in as the controller, open Flows, then Create scheduled flow.",
            "Name it 'Monthly profitability review' and paste the six steps of flow.steps.",
            "Set the schedule to the third working day of the month, at 07:00 UTC.",
            "Add the sources: the dashboards EF-TDB-01, EF-TDB-03, EF-TDB-04 and the topic.",
            "Add the destinations: the e-mail of the direction and the project space marge_project.",
            "Run it once on a past month and check the figures against the dashboards.",
        ),
        reference="docs/SPEC.fr.md chapter 14.4 and chapter 22",
    ),
    ManualAction(
        action_id="MA-SPACE",
        resource="Project space with the contracts (EF-AGT-01)",
        description=(
            "The contracts space holds the PDF contracts of the clients and is the knowledge "
            "source the agent quotes from. It is created in the console so that its memberships "
            "stay under the control of the administrator."
        ),
        steps=(
            "Open Spaces, then Create space, and name it marge_project.",
            "Add the S3 bucket of the contracts as a knowledge source, read only.",
            "Give access to the agent and to the controller, and to nobody else.",
            "Check on a contract that the agent quotes the clause with its article number.",
        ),
        reference="docs/SPEC.fr.md chapter 13.1 and chapter 22",
    ),
    ManualAction(
        action_id="MA-TOPIC",
        resource="Semantic layer, fallback if the API is not exposed",
        description=(
            "When the account does not expose the topic API, the semantic layer is declared in "
            "the console from the topic section of the bundle."
        ),
        steps=(
            "Open the Quick console, then the topic marge_topic.",
            "Declare the twelve metrics of topic.metrics with their definition and their unit.",
            "Declare the synonyms of topic.synonyms so that 'rentabilite', 'marge', 'profit' and "
            "'margin' all resolve to the margin metric.",
            "Declare the five joins of topic.joins between the datasets.",
            "Check that the default aggregations of topic.default_aggregations are the ones of "
            "the specification.",
        ),
        reference="docs/SPEC.fr.md chapter 14.1 and point 9 of chapter 24",
    ),
)


def _dataset_steps(bundle: dict[str, Any]) -> list[DeployStep]:
    """Steps that create the data source and the five datasets."""
    steps: list[DeployStep] = []
    datasets = bundle.get("datasets", [])
    first = datasets[0] if datasets else {}
    steps.append(
        DeployStep(
            order=1,
            action="create_data_source",
            resource="quicksight_data_source",
            description="Athena data source pointing at the curated S3 zone.",
            parameters={
                "aws_account_id": "${AWS_ACCOUNT_ID}",
                "region": bundle.get("account", {}).get("region", DEFAULT_REGION),
                "work_group": "primary",
                "role_arn": "${QUICKSIGHT_ATHENA_ROLE_ARN}",
                "first_table": first.get("name", "marge_client_mois"),
                "s3_uri": "s3://marge-curated/marge/",
            },
            api="quicksight:CreateDataSource",
        )
    )
    for index, dataset in enumerate(datasets, start=2):
        steps.append(
            DeployStep(
                order=index,
                action="create_dataset",
                resource=f"quicksight_dataset:{dataset.get('name')}",
                description=f"{dataset.get('grain')} — {dataset.get('description', '')}",
                parameters={
                    "data_source_id": "${DATA_SOURCE_ID}",
                    "name": dataset.get("name"),
                    "sql": dataset.get("sql"),
                    "keys": dataset.get("keys", []),
                    "fields": [f.get("name") for f in dataset.get("fields", [])],
                },
                api="quicksight:CreateDataSet",
            )
        )
    return steps


def _topic_step(bundle: dict[str, Any]) -> DeployStep:
    """Step that creates the semantic layer."""
    topic = bundle.get("topic", {})
    return DeployStep(
        order=len(bundle.get("datasets", [])) + 2,
        action="create_topic",
        resource=f"quicksight_topic:{topic.get('name')}",
        description=topic.get("description", ""),
        parameters={
            "datasets": topic.get("datasets", []),
            "metrics": [m.get("name") for m in topic.get("metrics", [])],
            "synonyms": {s.get("term"): s.get("metric") for s in topic.get("synonyms", [])},
            "joins": [
                {"left": j.get("left"), "right": j.get("right"), "on": j.get("on", [])}
                for j in topic.get("joins", [])
            ],
        },
        api="quicksight:CreateTopic",
    )


def _dashboard_steps(bundle: dict[str, Any]) -> list[DeployStep]:
    """Steps that create the six dashboards."""
    steps: list[DeployStep] = []
    dashboards = bundle.get("dashboards", [])
    base = len(bundle.get("datasets", [])) + 3
    for index, dashboard in enumerate(dashboards, start=base):
        steps.append(
            DeployStep(
                order=index,
                action="create_dashboard",
                resource=f"quicksight_dashboard:{dashboard.get('dashboard_id')}",
                description=dashboard.get("description", ""),
                parameters={
                    "name": dashboard.get("title"),
                    "requirement": dashboard.get("requirement"),
                    "datasets": dashboard.get("datasets", []),
                    "widgets": [
                        {
                            "name": w.get("name"),
                            "type": w.get("widget_type"),
                            "dataset": w.get("dataset"),
                            "fields": w.get("fields", []),
                            "measures": w.get("measures", []),
                            "filters": w.get("filters", []),
                        }
                        for w in dashboard.get("widgets", [])
                    ],
                    "row_filter_rules": dashboard.get("row_filter_rules", []),
                },
                api="quicksight:CreateDashboard",
            )
        )
    return steps


def _rls_steps(bundle: dict[str, Any]) -> list[DeployStep]:
    """Steps that apply the row-level rules."""
    steps: list[DeployStep] = []
    rules = bundle.get("rls_rules", [])
    base = len(bundle.get("datasets", [])) + len(bundle.get("dashboards", [])) + 3
    for index, rule in enumerate(rules, start=base):
        steps.append(
            DeployStep(
                order=index,
                action="apply_rls",
                resource=f"quicksight_rls:{rule.get('rule_id')}",
                description=rule.get("description", ""),
                parameters={
                    "identity_parameter": rule.get("identity_parameter"),
                    "identity_source": rule.get("identity_source"),
                    "role_values": {role: list(values) for role, values in rule.get("role_values", [])},
                    "protected_datasets": rule.get("protected_datasets", []),
                    "protected_fields": rule.get("protected_fields", []),
                },
                api="quicksight:CreateDataSet (RowLevelPermissionDataSet)",
            )
        )
    return steps


def build_plan(bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the whole deployment plan, without calling AWS."""
    payload = bundle if bundle is not None else to_asset_bundle()
    steps = [*_dataset_steps(payload), _topic_step(payload)]
    steps += [*_dashboard_steps(payload), *_rls_steps(payload)]
    steps.sort(key=lambda step: step.order)
    return {
        "account": payload.get("account", {"name": ACCOUNT_NAME, "region": DEFAULT_REGION}),
        "generated_by": "marge.quicksight.deploy.build_plan",
        "programmable_steps": [to_jsonable(step) for step in steps],
        "manual_actions": [to_jsonable(action) for action in MANUAL_ACTIONS],
    }


def write_plan(directory: str | Path, bundle: dict[str, Any] | None = None) -> Path:
    """Write the deployment plan as JSON in ``directory``."""
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    path = target / DEFAULT_PLAN_NAME
    path.write_text(
        json.dumps(build_plan(bundle), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def _dataset_payloads(bundle: dict[str, Any], options: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the per-dataset payloads of the live deployment."""
    return [
        {
            "aws_account_id": options["aws_account_id"],
            "dataset_id": options["dataset_ids"][dataset["name"]],
            "data_source_arn": options["data_source_arn"],
            "name": dataset["name"],
            "sql": dataset["sql"],
            "columns": dataset["fields"],
        }
        for dataset in bundle.get("datasets", [])
    ]


def _dashboard_payloads(bundle: dict[str, Any], options: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the per-dashboard payloads of the live deployment."""
    return [
        {
            "aws_account_id": options["aws_account_id"],
            "dashboard_id": options["dashboard_ids"][dashboard["dashboard_id"]],
            "name": dashboard["title"],
            "description": dashboard["description"],
            "source_entity": {
                "SourcePath": (
                    f"arn:aws:quicksight:{options.get('region', DEFAULT_REGION)}:"
                    f"{options['aws_account_id']}:dashboard/"
                    f"{options['dashboard_ids'][dashboard['dashboard_id']]}"
                )
            },
        }
        for dashboard in bundle.get("dashboards", [])
    ]


def deploy(options: dict[str, Any], bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Deploy the bundle to AWS with the Quick Sight API.

    ``options`` carries the AWS account identifier, the role and the
    credentials of the Athena data source, and the identifiers of the created
    resources. Every created resource is returned, so the caller can write the
    identifiers back into the bundle.
    """
    payload = bundle if bundle is not None else to_asset_bundle()
    api = quick_api.client(options.get("region", DEFAULT_REGION))
    created: dict[str, Any] = {
        "data_source": quick_api.create_data_source(api, options["data_source"]),
        "datasets": [quick_api.create_dataset(api, spec) for spec in _dataset_payloads(payload, options)],
        "dashboards": [
            quick_api.create_dashboard(api, spec) for spec in _dashboard_payloads(payload, options)
        ],
    }
    created["topic"] = quick_api.create_topic(
        api,
        {
            "aws_account_id": options["aws_account_id"],
            "topic_id": options.get("topic_id", "marge_topic"),
            "name": payload["topic"]["name"],
            "description": payload["topic"]["description"],
            "datasets": [
                {
                    "DataSetArn": options["dataset_arns"][name],
                    "DataSetName": name,
                }
                for name in payload["topic"]["datasets"]
            ],
            "custom_instructions": payload["topic"]["description"],
        },
    )
    return created


def main(argv: list[str] | None = None) -> int:
    """Entry point: ``python -m marge.quicksight.deploy --dry-run``."""
    parser = argparse.ArgumentParser(description="Deploy the Marge Quick assets")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="write the plan without calling AWS (default)",
    )
    parser.add_argument(
        "--out",
        default="infra/quicksight-assets",
        help="directory where the plan is written",
    )
    args = parser.parse_args(argv)
    path = write_plan(args.out)
    print(f"PLAN {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
