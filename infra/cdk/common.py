"""Shared building blocks of the Marge CDK application.

Only the AWS CDK is imported here; it is declared in ``requirements.txt``. The
CI pull-request worker has no node and no ``aws_cdk``: this code is linted but
never imported by the tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aws_cdk import Duration, Stack, Tags
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3

__all__ = [
    "PROJECT_NAME",
    "MargeStack",
    "environment_name",
    "secure_bucket",
    "tag_stack",
]

PROJECT_NAME = "marge"
"""Name of the project, used as a prefix on every resource."""


def environment_name(environment: str) -> str:
    """Normalise an environment name into a short, safe suffix."""
    return environment.strip().lower().replace(" ", "-")


BUILD_DIR = Path(__file__).resolve().parent / ".build"


def lambda_package(name: str, placeholder: str = "") -> lambda_.Code:
    """Code of one Lambda: the built package, or a stub when it is missing.

    ``scripts/build-lambda-package.sh`` assembles ``infra/cdk/.build/<name>``
    with the ``marge`` package and its runtime dependencies vendored in place,
    so ``import marge.lambdas...`` works once unzipped at ``/var/task``.

    Synthesis must never require that build (the CI worker has neither the
    assets nor Docker): when the directory is absent the function falls back to
    an inline stub that says so at invocation time instead of pretending to
    serve the portal.
    """
    directory = BUILD_DIR / name
    if (directory / "marge").is_dir():
        return lambda_.Code.from_asset(str(directory))
    body = placeholder or (
        "def handler(event, context):\n"
        "    return {'statusCode': 501, 'body': 'run scripts/build-lambda-package.sh'}\n"
    )
    return lambda_.Code.from_inline(body)


def secure_bucket(scope: Any, name: str, *, versioned: bool = True) -> s3.Bucket:
    """Create an encrypted, private S3 bucket with versioning."""
    return s3.Bucket(
        scope,
        name,
        encryption=s3.BucketEncryption.S3_MANAGED,
        block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        versioned=versioned,
        enforce_ssl=True,
        auto_delete_objects=False,
    )


def tag_stack(stack: Stack, environment: str) -> None:
    """Apply the common tags of the project to every resource of the stack."""
    Tags.of(stack).add("project", PROJECT_NAME)
    Tags.of(stack).add("environment", environment)
    Tags.of(stack).add("managed_by", "cdk")


class MargeStack(Stack):
    """Base class of every Marge stack: same tags, same naming, same timeout."""

    def __init__(
        self,
        scope: Any,
        construct_id: str,
        *,
        environment: str = "dev",
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.project = PROJECT_NAME
        self.env_name = environment
        self.qualifier = f"{PROJECT_NAME}-{environment_name(environment)}"
        tag_stack(self, environment)

    def service_role(
        self,
        construct_id: str,
        *,
        service: str,
        description: str,
        managed_policies: list[iam.IManagedPolicy] | None = None,
        statements: list[iam.PolicyStatement] | None = None,
    ) -> iam.Role:
        """Create a service role with the standard boundaries of the project."""
        inline = {"marge": iam.PolicyDocument(statements=statements)} if statements else {}
        return iam.Role(
            self,
            construct_id,
            assumed_by=iam.ServicePrincipal(service),
            description=description,
            managed_policies=managed_policies or [],
            inline_policies=inline,
        )

    def default_timeout(self) -> Duration:
        """Default timeout of the lambdas of this stack."""
        return Duration.seconds(60)


ATHENA_QUERY_ACTIONS = (
    "athena:StartQueryExecution",
    "athena:GetQueryExecution",
    "athena:GetQueryResults",
    "athena:GetQueryResultsStream",
    "athena:StopQueryExecution",
    "athena:BatchGetQueryExecution",
    "athena:ListQueryExecutions",
    "athena:GetWorkGroup",
)

GLUE_READ_ACTIONS = (
    "glue:GetDatabase",
    "glue:GetDatabases",
    "glue:GetTable",
    "glue:GetTables",
    "glue:GetPartition",
    "glue:GetPartitions",
    "glue:BatchGetPartition",
)


def analytical_query_statements(curated_bucket_name: str = "") -> list[iam.PolicyStatement]:
    """Least-privilege statements to query the curated zone through Athena.

    Replaces the AWS managed policies ``AmazonQuickSightAthenaAccess`` and
    ``AmazonQuickSightSpatialAccess``, both retired by AWS (``GetPolicy``
    returns 404, verified on account 710332178565 on 2026-11-11: the deploy
    failed with "does not exist or is not attachable"). It also avoids the
    wildcard actions of ``AmazonAthenaFullAccess`` and
    ``AWSGlueConsoleFullAccess``, which ENF-SEC-01 forbids.
    """
    statements = [
        iam.PolicyStatement(actions=list(ATHENA_QUERY_ACTIONS), resources=["*"]),
        iam.PolicyStatement(actions=list(GLUE_READ_ACTIONS), resources=["*"]),
    ]
    if curated_bucket_name:
        statements.append(
            iam.PolicyStatement(
                actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:GetBucketLocation"],
                resources=[
                    f"arn:aws:s3:::{curated_bucket_name}",
                    f"arn:aws:s3:::{curated_bucket_name}/athena-results/*",
                ],
            )
        )
    return statements
