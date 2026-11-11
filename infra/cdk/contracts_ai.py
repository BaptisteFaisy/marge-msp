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

import sys
from pathlib import Path
from typing import Any

from aws_cdk import CfnOutput, Duration
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from common import MargeStack, lambda_package

# Le plan de champs de l'annexe B vit dans le code applicatif : le CDK l'importe
# au lieu d'en entretenir une copie, sinon le blueprint et l'extracteur divergent.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from marge.contracts.schema import blueprint_schema

__all__ = ["ContractsAiStack"]

# Identifiant de *profil d'inférence* régional : Bedrock refuse l'invocation
# on-demand d'un modèle nu (« Retry your request with the ID or ARN of an
# inference profile »). Vérifié en réel sur eu-west-1 le 2026-11-11.
_MODEL_ID = "eu.amazon.nova-lite-v1:0"
"""Small, cheap Bedrock model used for the classification of the work."""


_INVOKE_ACTIONS = (
    "bedrock:InvokeModel",
    "bedrock:InvokeModelWithResponseStream",
    "bedrock:InvokeDataAutomation",
)
"""Actions the classification lambda needs on Bedrock."""

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
        raw_bucket_name: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, environment=environment, **kwargs)
        self.table_name = table_name
        self.raw_bucket_name = raw_bucket_name
        self.model_id = _MODEL_ID
        self.inference_profile_arn = inference_profile_arn
        self.bedrock_role = self._create_bedrock_role()
        self.classifier = self._create_classifier()
        self.blueprint = self.contract_blueprint(blueprint_schema())
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
        """Role assumed by the extraction and classification lambdas.

        Bedrock invocation plus, on the raw bucket only: read the contract PDFs
        and write the data automation output. Without the S3 grant the extractor
        dies with ``AccessDenied ... s3:GetObject`` on the very first call
        (observed on account 710332178565, 2026-11-11).
        """
        statements = [iam.PolicyStatement(actions=list(_INVOKE_ACTIONS), resources=["*"])]
        statements += self._raw_bucket_statements()
        return self.service_role(
            "BedrockRole",
            service="lambda.amazonaws.com",
            description="Calls Bedrock Data Automation and the Bedrock classifier.",
            statements=statements,
        )

    def _raw_bucket_statements(self) -> list[iam.PolicyStatement]:
        """Least-privilege access to the raw contract bucket."""
        if not self.raw_bucket_name:
            return []
        arn = f"arn:aws:s3:::{self.raw_bucket_name}"
        return [
            iam.PolicyStatement(actions=["s3:ListBucket"], resources=[arn]),
            iam.PolicyStatement(actions=["s3:GetObject"], resources=[f"{arn}/contracts/*"]),
            iam.PolicyStatement(actions=["s3:PutObject"], resources=[f"{arn}/contracts-output/*"]),
        ]

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
                "MARGE_INFERENCE_PROFILE": "standard",
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

    def contract_blueprint(self, schema: dict[str, Any]) -> bedrock.CfnBlueprint:
        """Declare the Bedrock Data Automation blueprint of the Annex B plan.

        ``schema`` is the document produced by
        ``marge.contracts.schema.blueprint_schema``: a ``class``, a
        ``description`` and ``properties`` mapping each field onto
        ``{type, inferenceType, instruction}``. That is the shape the API
        accepts — a ``{"fields": {...}}`` payload is rejected with "Request has
        invalid blueprint schema". The blueprint is applied to the PDF contracts
        in S3; every extracted field keeps its source passage so the controller
        can validate it (EF-CTR-02).
        """
        return bedrock.CfnBlueprint(
            self,
            "ContractFieldsBlueprint",
            blueprint_name=f"{self.qualifier}-contract-fields",
            type="DOCUMENT",
            schema=schema,
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
            standard_output_configuration=self._standard_output(),
        )

    @staticmethod
    def _standard_output() -> Any:
        """Standard output configuration of the data automation project.

        The API rejects a project without it ("Value at
        'standardOutputConfiguration' ... must not be null"), even when the
        blueprint supplies every field we need. The document standard extraction
        is what carries the source passages shown next to each extracted field
        in the portal (EF-CTR-02): bounding boxes on, key-value and table
        granularity (DOCUMENT + ELEMENT), Markdown text output.
        """
        prop = bedrock.CfnDataAutomationProject
        return prop.StandardOutputConfigurationProperty(
            document=prop.DocumentStandardOutputConfigurationProperty(
                extraction=prop.DocumentStandardExtractionProperty(
                    granularity=prop.DocumentExtractionGranularityProperty(
                        # Valeurs acceptées par CloudFormation : DOCUMENT, PAGE,
                        # ELEMENT, WORD, LINE. DOCUMENT + ELEMENT donne le texte
                        # et les passages sources sans descendre au mot.
                        types=["DOCUMENT", "ELEMENT"]
                    ),
                    bounding_box=prop.DocumentBoundingBoxProperty(state="ENABLED"),
                ),
                generative_field=prop.DocumentStandardGenerativeFieldProperty(state="ENABLED"),
                output_format=prop.DocumentOutputFormatProperty(
                    additional_file_format=prop.DocumentOutputAdditionalFileFormatProperty(state="ENABLED"),
                    text_format=prop.DocumentOutputTextFormatProperty(types=["MARKDOWN"]),
                ),
            )
        )

    def _outputs(self) -> None:
        """Expose the identifiers the deployment pipeline needs."""
        CfnOutput(self, "ClassifierFunctionName", value=self.classifier.function_name)
        CfnOutput(self, "ContractExtractorFunctionName", value=self.extractor.function_name)
        CfnOutput(self, "ModelId", value=self.model_id)
        # `standard` : Bedrock n'accepte que standard|optimized pour
        # performanceConfigLatency ; le tarif Flex passerait par un profil
        # d'inférence dédié, indisponible sur ce compte en eu-west-1.
        CfnOutput(self, "InferenceProfile", value=self.inference_profile_arn or "standard")
