"""Data lake stack: S3 zones, Glue catalog and Athena workgroup.

Implements the analytical half of the architecture of spec 11.2: the raw zone,
the curated zone that holds the common model, the Glue catalog and the Athena
workgroup used by the nightly recalculation.
"""

from __future__ import annotations

from typing import Any

from aws_cdk import CfnOutput, Duration
from aws_cdk import aws_athena as athena
from aws_cdk import aws_glue as glue
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from common import MargeStack, secure_bucket

__all__ = ["DataLakeStack"]

_ATHENA_MANAGED = iam.ManagedPolicy.from_aws_managed_policy_name("AmazonAthenaFullAccess")
_GLUE_MANAGED = iam.ManagedPolicy.from_aws_managed_policy_name("AWSGlueConsoleFullAccess")
_QUICKSIGHT_ATHENA = iam.ManagedPolicy.from_aws_managed_policy_name("AmazonQuickSightAthenaAccess")


class DataLakeStack(MargeStack):
    """Buckets, Glue catalog and Athena workgroup of the data lake."""

    def __init__(self, scope: Any, construct_id: str, *, environment: str = "dev", **kwargs: Any):
        super().__init__(scope, construct_id, environment=environment, **kwargs)
        self.raw_bucket = secure_bucket(self, f"{self.qualifier}-raw")
        self.curated_bucket = secure_bucket(self, f"{self.qualifier}-curated")
        self.database = self._create_database()
        self.athena_role = self._create_athena_role()
        self.workgroup = self._create_workgroup()
        self._create_crawler_role()
        self._add_lifecycle_rules()
        self._outputs()

    def _create_database(self) -> glue.CfnDatabase:
        """Create the Glue database that holds the common model."""
        return glue.CfnDatabase(
            self,
            "MargeDatabase",
            catalog_id=self.account,
            database_input=glue.CfnDatabase.DatabaseInputProperty(
                name="marge",
                description="Common model of Marge: clients, contracts, work, costs and margins.",
                location_uri=f"s3://{self.curated_bucket.bucket_name}/marge/",
            ),
        )

    def _create_athena_role(self) -> iam.Role:
        """Create the role Athena and Quick Sight use to query the curated zone."""
        role = self.service_role(
            "AthenaRole",
            service="glue.amazonaws.com",
            description="Reads the curated zone for the nightly recalculation and for Quick Sight.",
            managed_policies=[_ATHENA_MANAGED, _QUICKSIGHT_ATHENA],
        )
        self.curated_bucket.grant_read(role)
        self.raw_bucket.grant_read(role)
        return role

    def _create_workgroup(self) -> athena.CfnWorkGroup:
        """Create the Athena workgroup that caps the cost of a recalculation."""
        return athena.CfnWorkGroup(
            self,
            "MargeWorkGroup",
            name="marge",
            state="ENABLED",
            work_group_configuration=athena.CfnWorkGroup.WorkGroupConfigurationProperty(
                enforce_work_group_configuration=True,
                publish_cloud_watch_metrics_enabled=True,
                bytes_scanned_cutoff_per_query=10 * 1024 * 1024 * 1024,
                result_configuration=athena.CfnWorkGroup.ResultConfigurationProperty(
                    output_location=f"s3://{self.curated_bucket.bucket_name}/athena-results/",
                    encryption_configuration=athena.CfnWorkGroup.EncryptionConfigurationProperty(
                        encryption_option="SSE_S3",
                    ),
                ),
                engine_version=athena.CfnWorkGroup.EngineVersionProperty(
                    selected_engine_version="AUTO",
                ),
            ),
        )

    def _create_crawler_role(self) -> iam.Role:
        """Create the role the Glue crawler uses to read the raw zone."""
        crawler_role = self.service_role(
            "CrawlerRole",
            service="glue.amazonaws.com",
            description="Reads the raw zone to refresh the catalog.",
            managed_policies=[_GLUE_MANAGED],
        )
        self.raw_bucket.grant_read(crawler_role)
        return crawler_role

    def _add_lifecycle_rules(self) -> None:
        """Expire the raw objects after one year to bound the storage cost."""
        self.raw_bucket.add_lifecycle_rule(
            expiration=Duration.days(365),
            transitions=[
                s3.Transition(
                    storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                    transition_after=Duration.days(30),
                )
            ],
            abort_incomplete_multipart_upload_after=Duration.days(7),
        )

    def _outputs(self) -> None:
        """Expose the names the other stacks need."""
        CfnOutput(self, "RawBucketName", value=self.raw_bucket.bucket_name)
        CfnOutput(self, "CuratedBucketName", value=self.curated_bucket.bucket_name)
        CfnOutput(self, "DatabaseName", value="marge")
        CfnOutput(self, "WorkGroup", value="marge")
