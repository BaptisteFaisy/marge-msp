"""Portal stack: CloudFront, API Gateway, Lambda and Cognito.

Implements the validation portal of spec 16 and of EF-VAL-01: the controller
validates the client matches, the contract clauses and the work classifications
from a browser. Every validation keeps its author, its date and its reason
(EF-VAL-02).
"""

from __future__ import annotations

from typing import Any

from aws_cdk import CfnOutput, Duration
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from common import MargeStack, python_inline, secure_bucket

__all__ = ["PortalStack"]

ROLES: dict[str, str] = {
    "EXECUTIVE": "Direction of the MSP",
    "OPERATIONS_DIRECTOR": "Director of operations",
    "ACCOUNT_MANAGER": "Account manager",
    "CONTROLLER": "Controller",
    "ADMINISTRATOR": "Administrator",
}
"""The five roles of spec 6, one Cognito group each."""

_API_BODY = """
import json


def handler(event, context):
    \"\"\"Placeholder: the real API lives in ``marge.api``.\"\"\"
    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"routes": ["/v1/matches", "/v1/contracts", "/v1/classifications"]}),
    }
"""


class PortalStack(MargeStack):
    """Validation portal: static site, API and identity provider."""

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
        self.user_pool = self._create_user_pool()
        self.api_role = self._create_api_role()
        self.api_function = self._create_api_function()
        self.api = self._create_api()
        self.distribution = self._create_distribution()
        self._outputs()

    def _create_user_pool(self) -> cognito.UserPool:
        """Create the user pool and one group per role of spec 6."""
        pool = cognito.UserPool(
            self,
            "PortalUserPool",
            user_pool_name=f"{self.qualifier}-portal",
            sign_in_aliases=cognito.SignInAliases(email=True),
            self_sign_up_enabled=False,
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True,
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            mfa=cognito.Mfa.OPTIONAL,
            mfa_second_factor=cognito.MfaSecondFactor(sms=False, otp=True),
        )
        for role, description in ROLES.items():
            pool.add_group(f"Group{role.title().replace('_', '')}", group_name=role, description=description)
        return pool

    def _create_api_role(self) -> iam.Role:
        """Role of the API lambda: read and write on the validation table."""
        return self.service_role(
            "ApiRole",
            service="lambda.amazonaws.com",
            description="Runs the validation portal API.",
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "dynamodb:GetItem",
                        "dynamodb:PutItem",
                        "dynamodb:UpdateItem",
                        "dynamodb:Query",
                        "dynamodb:Scan",
                    ],
                    resources=[f"arn:aws:dynamodb:{self.region}:{self.account}:table/{self.table_name}"],
                )
            ],
        )

    def _create_api_function(self) -> lambda_.Function:
        """Create the lambda behind the API Gateway."""
        return lambda_.Function(
            self,
            "PortalApiFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=python_inline(_API_BODY),
            timeout=Duration.seconds(30),
            memory_size=1024,
            role=self.api_role,
            environment={
                "TABLE_NAME": self.table_name,
                "READ_ONLY_ROLES": "EXECUTIVE,OPERATIONS_DIRECTOR",
            },
            description="Validation portal API: matches, contracts, classifications, rates.",
        )

    def _create_api(self) -> apigw.RestApi:
        """Create the REST API of spec 16 behind an authorizer."""
        api = apigw.RestApi(
            self,
            "PortalApi",
            rest_api_name=f"{self.qualifier}-portal",
            description="Validation portal API of Marge (spec 16).",
            deploy_options=apigw.StageOptions(stage_name="prod", tracing_enabled=True),
        )
        authorizer = apigw.CognitoUserPoolsAuthorizer(
            self,
            "PortalAuthorizer",
            cognito_user_pools=[self.user_pool],
            authorizer_name="portal-cognito",
        )
        integration = apigw.LambdaIntegration(self.api_function)
        resources: dict[str, apigw.Resource] = {}
        for template, methods in _API_ROUTES:
            resource = _resource_for(api.root, resources, template)
            for method in methods:
                resource.add_method(
                    method,
                    integration,
                    authorizer=authorizer,
                    authorization_type=apigw.AuthorizationType.COGNITO,
                )
        return api

    def _create_distribution(self) -> cloudfront.Distribution:
        """Create the CloudFront distribution serving the static portal."""
        site_bucket = secure_bucket(self, f"{self.qualifier}-portal-site")
        origin = origins.S3BucketOrigin.with_origin_access_control(site_bucket)
        distribution = cloudfront.Distribution(
            self,
            "PortalDistribution",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origin,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
            ],
            enable_ipv6=True,
            http_version=cloudfront.HttpVersion.HTTP2,
        )
        CfnOutput(self, "PortalSiteBucket", value=site_bucket.bucket_name)
        return distribution

    def _outputs(self) -> None:
        """Expose the URLs the demo needs."""
        CfnOutput(self, "PortalUrl", value=f"https://{self.distribution.distribution_domain_name}")
        CfnOutput(self, "ApiUrl", value=self.api.url)
        CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id)
        CfnOutput(
            self, "UserPoolClientId", value=self.user_pool.add_client("portal-client").user_pool_client_id
        )


_API_ROUTES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("matches", ("GET",)),
    ("matches/{id}/decision", ("POST",)),
    ("contracts", ("GET",)),
    ("contracts/{id}", ("GET",)),
    ("contracts/{id}/fields", ("PUT",)),
    ("contracts/{id}/validate", ("POST",)),
    ("classifications", ("GET",)),
    ("classifications/{id}/decision", ("POST",)),
    ("rates", ("GET", "PUT")),
    ("allocation-rules", ("GET", "PUT")),
    ("coverage", ("GET",)),
    ("recalculate", ("POST",)),
)
"""The routes of spec 16."""


def _resource_for(root: apigw.Resource, cache: dict[str, apigw.Resource], template: str) -> apigw.Resource:
    """Walk the path template and return the deepest API Gateway resource.

    ``cache`` keeps the resources already created, so that two templates
    sharing a prefix (``matches`` and ``matches/{id}/decision``) reuse the
    same resource object instead of creating it twice.
    """
    resource = root
    for part in template.split("/"):
        if not part:
            continue
        path = f"{resource.path}/{part}"
        if path not in cache:
            cache[path] = resource.add_resource(part)
        resource = cache[path]
    return resource
