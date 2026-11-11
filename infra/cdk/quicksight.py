"""Quick Sight stack: IAM role, asset bucket and dashboard assets.

Implements the analytical part of spec 11.2: the IAM role Quick Sight uses to
read the curated zone through Athena, and the bucket that carries the asset
bundle produced by ``marge.quicksight.to_asset_bundle`` and replayed by
``marge.quicksight.deploy``.

The row-level rules of EF-TDB-06 are enforced by Quick Sight itself, through
the identity parameter declared in ``marge.quicksight.rls``.
"""

from __future__ import annotations

from typing import Any

from aws_cdk import CfnOutput, Duration
from aws_cdk import aws_iam as iam
from common import MargeStack, secure_bucket

__all__ = ["QuickSightStack"]

_ATHENA_ACCESS = iam.ManagedPolicy.from_aws_managed_policy_name("AmazonQuickSightAthenaAccess")
_SPACIAL_ACCESS = iam.ManagedPolicy.from_aws_managed_policy_name("AmazonQuickSightSpatialAccess")


class QuickSightStack(MargeStack):
    """IAM role and asset bucket backing the Quick Sight assets."""

    def __init__(
        self,
        scope: Any,
        construct_id: str,
        *,
        environment: str = "dev",
        curated_bucket_name: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, environment=environment, **kwargs)
        self.curated_bucket_name = curated_bucket_name
        self.asset_bucket = secure_bucket(self, f"{self.qualifier}-quicksight-assets")
        self.service_role = self._create_service_role()
        self._grant_asset_bucket()
        self._outputs()

    def _create_service_role(self) -> iam.Role:
        """Create the role Quick Sight assumes to query the curated zone."""
        role = self.service_role(
            "QuickSightRole",
            service="quicksight.amazonaws.com",
            description="Reads the curated zone for the five analytical datasets.",
            managed_policies=[_ATHENA_ACCESS, _SPACIAL_ACCESS],
        )
        if self.curated_bucket_name:
            role.add_to_policy(
                iam.PolicyStatement(
                    actions=["s3:GetObject", "s3:ListBucket"],
                    resources=[
                        f"arn:aws:s3:::{self.curated_bucket_name}",
                        f"arn:aws:s3:::{self.curated_bucket_name}/*",
                    ],
                )
            )
        return role

    def _grant_asset_bucket(self) -> None:
        """Let the asset bucket be written by the deployment pipeline."""
        self.asset_bucket.add_lifecycle_rule(
            expiration=Duration.days(365),
            abort_incomplete_multipart_upload_after=Duration.days(7),
        )

    def _outputs(self) -> None:
        """Expose the identifiers the deployment pipeline needs."""
        CfnOutput(self, "AssetBucketName", value=self.asset_bucket.bucket_name)
        CfnOutput(self, "ServiceRoleArn", value=self.service_role.role_arn)
        CfnOutput(self, "AssetPrefix", value="marge-assets.json")
