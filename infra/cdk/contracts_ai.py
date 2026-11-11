"""Contracts and AI stack: Bedrock Data Automation and the Bedrock classifier.

Implements spec 13: the contracts are read by Bedrock Data Automation with a
custom field plan (Annex B), and the interventions are classified by a Bedrock
model invoked on the Flex tier, which gives a discount on the tolerant
nightly processing.

The model never produces a number (ENF-IA-01) and no extracted clause counts
before a human validates it (ENF-IA-02): the stack only declares the
blueprint, the project and the permissions.
"""

from __future__ import annotations

from typing import Any

from aws_cdk import CfnOutput, Duration
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from common import MargeStack, lambda_package

__all__ = ["ContractsAiStack"]

_MODEL_ID = "amazon.nova-lite-v1:0"
"""Small, cheap Bedrock model used for the classification of the work."""


_INVOKE_ACTIONS = (
    "bedrock:InvokeModel",
    "bedrock:InvokeModelWithResponseStream",
    "bedrock:InvokeDataAutomation",
)
"""Actions the classification lambda needs on Bedrock."""

ANNEX_B_FIELD_PLAN: dict[str, dict[str, str]] = {
    "customer_name": {"type": "STRING", "instruction": "The legal name of the customer."},
    "start_date": {"type": "STRING", "instruction": "The date the contract takes effect."},
    "end_date": {"type": "STRING", "instruction": "The end date of the contract."},
    "renewal_terms": {"type": "STRING", "instruction": "How and for how long the contract renews."},
    "termination_notice": {"type": "STRING", "instruction": "The notice required to terminate."},
    "monthly_subscription": {"type": "STRING", "instruction": "The monthly fee, excluding tax."},
    "currency": {"type": "STRING", "instruction": "The currency of the amounts."},
    "included_hours_per_month": {
        "type": "STRING",
        "instruction": "The number of hours included in the subscription, empty when unlimited.",
    },
    "extra_hour_rate": {"type": "STRING", "instruction": "The hourly rate beyond the quota."},
    "services_included": {"type": "STRING", "instruction": "The list of the services included."},
    "exclusions": {"type": "STRING", "instruction": "The list of the exclusions."},
    "service_hours": {"type": "STRING", "instruction": "The service windows, for example 24x7."},
    "sla_commitments": {"type": "STRING", "instruction": "The service level commitments."},
    "penalties": {"type": "STRING", "instruction": "How the penalties are computed."},
    "indexation_clause": {"type": "STRING", "instruction": "The price indexation clause."},
    "covered_accounts_or_resources": {
        "type": "STRING",
        "instruction": "The number of accounts or resources covered.",
    },
}
"""The field plan of Annex B, applied by Bedrock Data Automation (spec 13.1)."""


class ContractsAiStack(MargeStack):
    """Bedrock Data Automation blueprint and Bedrock model for the classification."""

    def __init__(
        self,
        scope: Any,
        construct_id: str,
        *,
        environment: str = "dev",
        inference_profile_arn: str = "",
        table_name: str = "marge",
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, environment=environment, **kwargs)
        self.table_name = table_name
        self.model_id = _MODEL_ID
        self.inference_profile_arn = inference_profile_arn
        self.bedrock_role = self._create_bedrock_role()
        self.classifier = self._create_classifier()
        self.blueprint = self.contract_blueprint(ANNEX_B_FIELD_PLAN)
        self.project = self.data_automation_project(self.blueprint)
        self.project.add_metadata(
            "CloudFormation-Validate::F3006",
            "Bedrock Data Automation is not available in every region yet; confirm the target "
            "region before deploying (docs/SPEC.fr.md chapter 24, point 2).",
        )
        self.extractor = self._create_extractor()
        self._grant_model_access()
        self._outputs()

    def _create_bedrock_role(self) -> iam.Role:
        """Role assumed by the classification lambda to call Bedrock."""
        return self.service_role(
            "BedrockRole",
            service="lambda.amazonaws.com",
            description="Calls Bedrock Data Automation and the Bedrock classifier.",
            statements=[
                iam.PolicyStatement(
                    actions=list(_INVOKE_ACTIONS),
                    resources=["*"],
                )
            ],
        )

    def _create_classifier(self) -> lambda_.Function:
        """Create the lambda that classifies the interventions overnight."""
        return lambda_.Function(
            self,
            "ClassifierFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="marge.lambdas.handlers.classify_handler",
            code=lambda_package("jobs"),
            timeout=Duration.minutes(10),
            memory_size=2048,
            role=self.bedrock_role,
            environment={
                "MARGE_TABLE": self.table_name,
                "MARGE_MODEL_ID": self.model_id,
                "MARGE_REGION": self.region,
                "INFERENCE_PROFILE_ARN": self.inference_profile_arn,
                # Bedrock n'accepte que `standard` ou `optimized` ici ; le tarif
                # Flex passe par un profil d'inférence, pas par ce réglage.
                "INFERENCE_PROFILE": "standard",
            },
            description="Classifies the interventions against the scope of the contract.",
        )

    def _create_extractor(self) -> lambda_.Function:
        """Read a contract PDF from S3 with Bedrock Data Automation (EF-CTR-01).

        The extracted fields land in ``EXTRACTED`` status: they never count
        before a human validates them in the portal (EF-CTR-03, ENF-IA-02).
        """
        return lambda_.Function(
            self,
            "ContractExtractorFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="marge.lambdas.handlers.contracts_handler",
            code=lambda_package("jobs"),
            timeout=Duration.minutes(5),
            memory_size=1024,
            role=self.bedrock_role,
            environment={
                "MARGE_TABLE": self.table_name,
                "MARGE_REGION": self.region,
                "MARGE_PROFILE_ARN": self.project.attr_project_arn,
            },
            description="Extracts the Annex B fields of a contract with its source passages.",
        )

    def _grant_model_access(self) -> None:
        """Let the classifier invoke the model and the data automation service."""
        self.classifier.add_to_role_policy(
            iam.PolicyStatement(
                actions=list(_INVOKE_ACTIONS),
                resources=["*"],
            )
        )
        self.classifier.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:PutInvocationProfile", "bedrock:GetInferenceProfile"],
                resources=["*"],
            )
        )

    def contract_blueprint(self, fields: dict[str, dict[str, str]]) -> bedrock.CfnBlueprint:
        """Declare the Bedrock Data Automation blueprint of the Annex B field plan.

        ``fields`` maps a field name onto its extraction instruction, for
        example ``{"monthly_subscription": {"type": "STRING",
        "instruction": "The monthly fee"}}``. The blueprint is applied to the
        PDF contracts stored in S3; every extracted field keeps its source
        passage so that the controller can validate it (EF-CTR-02).
        """
        return bedrock.CfnBlueprint(
            self,
            "ContractFieldsBlueprint",
            blueprint_name=f"{self.qualifier}-contract-fields",
            type="DOCUMENT",
            schema={"fields": fields},
        )

    def data_automation_project(self, blueprint: bedrock.CfnBlueprint) -> bedrock.CfnDataAutomationProject:
        """Declare the data automation project that applies the blueprint."""
        return bedrock.CfnDataAutomationProject(
            self,
            "ContractDataAutomationProject",
            project_name=f"{self.qualifier}-contracts",
            project_description="Reads the managed services contracts of the clients.",
            project_type="ASYNC",
            custom_output_configuration=bedrock.CfnDataAutomationProject.CustomOutputConfigurationProperty(
                blueprints=[
                    bedrock.CfnDataAutomationProject.BlueprintItemProperty(
                        blueprint_arn=blueprint.attr_blueprint_arn,
                    )
                ]
            ),
        )

    def _outputs(self) -> None:
        """Expose the identifiers the deployment pipeline needs."""
        CfnOutput(self, "ClassifierFunctionName", value=self.classifier.function_name)
        CfnOutput(self, "ContractExtractorFunctionName", value=self.extractor.function_name)
        CfnOutput(self, "ModelId", value=self.model_id)
        CfnOutput(self, "InferenceProfile", value="FLEX")
