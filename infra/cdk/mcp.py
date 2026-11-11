"""MCP stack: AgentCore Gateway and the lambda that exposes the actions.

Implements spec 14.3: three read-only or draft-only actions are exposed to
the Quick chat agent through an AgentCore Gateway:

* ``create_renegotiation_task`` — opens one renegotiation folder per client;
* ``draft_extra_billing_proposal`` — prepares a draft, never sends it;
* ``get_margin_breakdown`` — reads the margin broken down into its posts.

The actions never send anything to a customer on their own: the extra billing
proposal stays a draft (spec 14.3, risk of chapter 22).
"""

from __future__ import annotations

from typing import Any

from aws_cdk import CfnOutput, CfnResource, Duration
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from common import MargeStack, lambda_package

__all__ = ["McpStack"]


class McpStack(MargeStack):
    """AgentCore Gateway and the MCP lambda behind it."""

    def __init__(
        self,
        scope: Any,
        construct_id: str,
        *,
        environment: str = "dev",
        table_name: str = "marge-validations",
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, environment=environment, **kwargs)
        self.table_name = table_name
        self.mcp_role = self._create_mcp_role()
        self.mcp_function = self._create_mcp_function()
        self.gateway_role = self._create_gateway_role()
        self.gateway = self._create_gateway()
        self._outputs()

    def _create_mcp_role(self) -> iam.Role:
        """Role of the MCP lambda: read the margin, write a task in the ITSM tool."""
        return self.service_role(
            "McpRole",
            service="lambda.amazonaws.com",
            description="Serves the three MCP actions of spec 14.3.",
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "dynamodb:GetItem",
                        "dynamodb:Query",
                        "dynamodb:PutItem",
                        "dynamodb:UpdateItem",
                    ],
                    resources=[f"arn:aws:dynamodb:{self.region}:{self.account}:table/{self.table_name}"],
                ),
                iam.PolicyStatement(
                    actions=["execute-api:Invoke"],
                    resources=[f"arn:aws:execute-api:{self.region}:{self.account}:*/*/*/*"],
                ),
            ],
        )

    def _create_mcp_function(self) -> lambda_.Function:
        """Create the lambda that speaks the MCP protocol."""
        return lambda_.Function(
            self,
            "McpFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="marge.lambdas.handlers.mcp_handler",
            code=lambda_package("jobs"),
            timeout=Duration.seconds(30),
            memory_size=512,
            role=self.mcp_role,
            environment={
                "MARGE_TABLE": self.table_name,
                "MARGE_REGION": self.region,
                "MARGE_ROLE": "ACCOUNT_MANAGER",
            },
            description="MCP server: renegotiation task, billing draft, margin breakdown.",
        )

    def _create_gateway_role(self) -> iam.Role:
        """Role assumed by the AgentCore Gateway to reach the MCP lambda."""
        return self.service_role(
            "GatewayRole",
            service="bedrock-agentcore.amazonaws.com",
            description="Lets the AgentCore Gateway invoke the MCP lambda.",
            statements=[
                iam.PolicyStatement(
                    actions=["lambda:InvokeFunction"],
                    resources=[self.mcp_function.function_arn],
                )
            ],
        )

    def _create_gateway(self) -> CfnResource:
        """Create the AgentCore Gateway via CloudFormation resource."""
        return CfnResource(
            self,
            "MargeGateway",
            type="AWS::BedrockAgentCore::Gateway",
            properties={
                "Name": f"{self.qualifier}-gateway",
                "Description": "Gateway exposing the three Marge actions to the Quick chat agent.",
                "RoleArn": self.gateway_role.role_arn,
                "ProtocolType": "MCP",
                "AuthorizerType": "AWS_IAM",
            },
        )

    def _outputs(self) -> None:
        """Expose the identifiers the Quick agent configuration needs."""
        CfnOutput(self, "GatewayName", value=f"{self.qualifier}-gateway")
        CfnOutput(self, "McpFunctionName", value=self.mcp_function.function_name)
