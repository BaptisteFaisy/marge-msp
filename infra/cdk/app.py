"""Entry point of the Marge CDK application.

Usage::

    cd infra/cdk
    pip install -r requirements.txt
    python app.py

The application builds seven stacks, one per component of the architecture of
spec 11.2, then writes the CloudFormation templates in ``cdk.out``.

The CI pull-request worker has no node and no ``aws_cdk``: this file is
linted but never imported by the tests. The synthesis happens in the
``deploy-check`` workflow, after the merge on ``main``.
"""

from __future__ import annotations

import os
import sys

from aws_cdk import App, Environment

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from contracts_ai import ContractsAiStack
from data_lake import DataLakeStack
from mcp import McpStack
from observability import ObservabilityStack
from orchestration import OrchestrationStack
from portal import PortalStack
from quicksight import QuickSightStack

__all__ = ["build_app", "main"]


def build_app(context: dict[str, str] | None = None) -> App:
    """Build the CDK application with the seven stacks of the project."""
    env_name = (context or {}).get("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))
    app = App(context=context, outdir=os.environ.get("CDK_OUTDIR", "cdk.out"))
    env = Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
        # eu-west-3 (Paris) ne propose ni Bedrock Data Automation ni les agents
        # Bedrock : `cdk synth` le signale. eu-west-1 (Irlande) réunit Quick
        # Sight, Bedrock runtime, Bedrock Data Automation et Agents — c'est la
        # région de référence du projet (point 2 du chapitre 24 de la spec).
        region=os.environ.get("CDK_DEFAULT_REGION", "eu-west-1"),
    )
    data_lake = DataLakeStack(app, "MargeDataLake", environment=env_name, env=env)
    contracts_ai = ContractsAiStack(app, "MargeContractsAi", environment=env_name, env=env)
    portal = PortalStack(app, "MargePortal", environment=env_name, env=env)
    McpStack(app, "MargeMcp", environment=env_name, env=env)
    QuickSightStack(
        app,
        "MargeQuickSight",
        environment=env_name,
        env=env,
        curated_bucket_name=data_lake.curated_bucket.bucket_name,
    )
    observability = ObservabilityStack(app, "MargeObservability", environment=env_name, env=env)
    orchestration = OrchestrationStack(
        app,
        "MargeOrchestration",
        environment=env_name,
        env=env,
        table_name=portal.table_name,
        curated_bucket_name=data_lake.curated_bucket.bucket_name,
        alarm_topic=observability.topic,
    )
    contracts_ai.node.add_dependency(data_lake)
    portal.node.add_dependency(data_lake)
    orchestration.node.add_dependency(portal)
    orchestration.node.add_dependency(observability)
    return app


def main() -> None:
    """Synthesise the application."""
    app = build_app()
    app.synth()


if __name__ == "__main__":
    main()
