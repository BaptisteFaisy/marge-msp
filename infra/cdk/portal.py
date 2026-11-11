"""Portal stack: CloudFront, API Gateway, Lambda and Cognito.

Implements the validation portal of spec 16 and of EF-VAL-01: the controller
validates the client matches, the contract clauses and the work classifications
from a browser. Every validation keeps its author, its date and its reason
(EF-VAL-02).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aws_cdk import CfnOutput, Duration
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3_deployment as s3deploy
from common import MargeStack, lambda_package, secure_bucket

PORTAL_DIR = str(Path(__file__).resolve().parents[2] / "portal")

__all__ = ["PortalStack"]

ROLES: dict[str, str] = {
    "EXECUTIVE": "Direction of the MSP",
    "OPERATIONS_DIRECTOR": "Director of operations",
    "ACCOUNT_MANAGER": "Account manager",
    "CONTROLLER": "Controller",
    "ADMINISTRATOR": "Administrator",
}
"""The five roles of spec 6, one Cognito group each."""


class PortalStack(MargeStack):
    """Validation portal: static site, API and identity provider."""

    def __init__(
        self,
        scope: Any,
        construct_id: str,
        *,
        environment: str = "dev",
        table_name: str = "marge-validations",
        auth_mode: str = "dev",
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, environment=environment, **kwargs)
        self.table_name = table_name
        # `dev` : l'identité vient des en-têtes X-Actor-Id / X-Actor-Role, ce qui
        # permet aux juges d'utiliser les comptes de démonstration (EF-ADM-03).
        # `cognito` : l'autorisateur exige un jeton signé. Le user pool est créé
        # dans les deux cas ; seul le branchement de l'autorisateur change.
        self.auth_mode = auth_mode
        self.user_pool = self._create_user_pool()
        self.api_role = self._create_api_role()
        self.api_function = self._create_api_function()
        self.api = self._create_api()
        self.distribution = self._create_distribution()
        self._deploy_site()
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
            handler="marge.lambdas.handlers.portal_handler",
            code=lambda_package("portal"),
            timeout=Duration.seconds(30),
            memory_size=1024,
            role=self.api_role,
            environment={
                "MARGE_TABLE": self.table_name,
                "MARGE_REGION": self.region,
                "MARGE_AUTH_MODE": "cognito",
                "MARGE_PORTAL_DIR": "/var/task/portal",
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
        # Un autorisateur non rattaché à une méthode fait échouer la synthèse
        # (« must be attached to a RestApi ») : il n'est créé qu'en mode cognito.
        authorizer = None
        if self.auth_mode == "cognito":
            authorizer = apigw.CognitoUserPoolsAuthorizer(
                self,
                "PortalAuthorizer",
                cognito_user_pools=[self.user_pool],
                authorizer_name="portal-cognito",
            )
        integration = apigw.LambdaIntegration(self.api_function)
        # Les routes du chapitre 16 sont sous /v1 : sans ce préfixe l'URL
        # publique /prod/v1/contracts répond « Missing Authentication Token ».
        v1 = api.root.add_resource("v1")
        resources: dict[str, apigw.Resource] = {}
        for template, methods in _API_ROUTES:
            resource = _resource_for(v1, resources, template)
            for method in methods:
                self._add_method(resource, method, integration, authorizer)
        return api

    def _add_method(
        self,
        resource: apigw.Resource,
        method: str,
        integration: apigw.LambdaIntegration,
        authorizer: apigw.CognitoUserPoolsAuthorizer | None,
    ) -> None:
        """Add one method, with the Cognito authorizer only in cognito mode."""
        if self.auth_mode == "cognito" and authorizer is not None:
            resource.add_method(
                method,
                integration,
                authorizer=authorizer,
                authorization_type=apigw.AuthorizationType.COGNITO,
            )
            return
        resource.add_method(method, integration)

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
            additional_behaviors={"/v1/*": self._api_behavior()},
            enable_ipv6=True,
            http_version=cloudfront.HttpVersion.HTTP2,
        )
        self.site_bucket = site_bucket
        CfnOutput(self, "PortalSiteBucket", value=site_bucket.bucket_name)
        return distribution

    def _deploy_site(self) -> None:
        """Upload ``portal/`` to the site bucket and invalidate CloudFront.

        Without it the distribution answers 403 on ``/``: the bucket exists but
        holds nothing. The invalidation keeps ``index.html`` fresh after a redeploy.
        """
        s3deploy.BucketDeployment(
            self,
            "DeployPortalSite",
            sources=[s3deploy.Source.asset(PORTAL_DIR)],
            destination_bucket=self.site_bucket,
            distribution=self.distribution,
            distribution_paths=["/*"],
            memory_limit=512,
        )

    def _api_behavior(self) -> cloudfront.BehaviorOptions:
        """Proxy ``/v1/*`` to API Gateway: one public URL, no CORS.

        The stage path (``/prod``) is the origin path, so the browser calls
        ``https://<cloudfront>/v1/contracts`` and CloudFront reaches
        ``/prod/v1/contracts``.
        """
        url = self.api.deployment_stage.url_for_path()
        host = url.split("//")[1].split("/")[0]
        stage = f"/{self.api.deployment_stage.stage_name}"
        return cloudfront.BehaviorOptions(
            origin=origins.HttpOrigin(host, origin_path=stage),
            allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
            cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
            origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
            viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        )

    def _outputs(self) -> None:
        """Expose the URLs the demo needs."""
        CfnOutput(self, "PortalUrl", value=f"https://{self.distribution.distribution_domain_name}")
        CfnOutput(
            self,
            "PortalApiNote",
            value="The portal calls /v1/* on its own origin: leave the API base field empty.",
        )
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
