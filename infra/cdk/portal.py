"""Portal stack: CloudFront, API Gateway, Lambda and Cognito.

Implements the validation portal of spec 16 and of EF-VAL-01: the controller
validates the client matches, the contract clauses and the work classifications
from a browser. Every validation keeps its author, its date and its reason
(EF-VAL-02).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from aws_cdk import CfnOutput, Duration, RemovalPolicy
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3_deployment as s3deploy
from common import MargeStack, lambda_package, secure_bucket

PORTAL_DIR = str(Path(__file__).resolve().parents[2] / "portal")

# La description de la table vit dans le code applicatif : le stack la lit au
# lieu d'en entretenir une copie (une seule source de vérité pour pk/sk et GSI).
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from marge.store.dynamo_store import create_table_resources  # noqa: E402

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
        self.table = self._create_table()
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

    def _create_table(self) -> dynamodb.Table:
        """The validation store: one table, three sparse GSIs, on-demand.

        Shape and indexes come from ``marge.store.dynamo_store``, so the CDK and
        the code that reads and writes the table cannot drift. On-demand billing
        and no provisioned capacity: nothing runs, nothing is billed while the
        demo is idle. Encryption at rest with an AWS managed key (ENF-SEC-01)
        and point-in-time recovery on.
        """
        spec = create_table_resources(self.table_name)
        table = dynamodb.Table(
            self,
            "ValidationTable",
            table_name=self.table_name,
            partition_key=dynamodb.Attribute(name="pk", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="sk", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            # Clé gérée par AWS : chiffrement au repos sans clé client à gérer
            # (ENF-SEC-01).
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.RETAIN,
        )
        for index in spec["GlobalSecondaryIndexes"]:
            table.add_global_secondary_index(
                index_name=index["IndexName"],
                partition_key=dynamodb.Attribute(
                    name=index["KeySchema"][0]["AttributeName"], type=dynamodb.AttributeType.STRING
                ),
                sort_key=dynamodb.Attribute(
                    name=index["KeySchema"][1]["AttributeName"], type=dynamodb.AttributeType.STRING
                ),
                projection_type=dynamodb.ProjectionType.ALL,
            )
        return table

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
                    resources=[self.table.table_arn, f"{self.table.table_arn}/index/*"],
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
                "MARGE_TABLE": self.table.table_name,
                "MARGE_REGION": self.region,
                # Suit le mode du stack : `dev` lit l'identité dans les
                # en-têtes X-Actor-* (comptes de démonstration des juges,
                # EF-ADM-03), `cognito` exige un jeton signé et refuse toute
                # requête sans clé de vérification configurée (spec 17).
                "MARGE_AUTH_MODE": self.auth_mode,
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
            default_method_options=_default_method_options(self.auth_mode, self.user_pool),
        )
        integration = apigw.LambdaIntegration(self.api_function)
        # Une permission `lambda:InvokeFunction` par méthode faisait dépasser la
        # limite AWS de 20 480 octets sur la policy de ressource de la fonction
        # (14 routes x ~1,4 Ko). Le motif proxy ANY délégue le routage à
        # FastAPI : deux permissions suffisent, et la table des routes du
        # chapitre 16 reste vérifiée par tests/unit/api/test_route_table.py
        # contre l'OpenAPI de l'application.
        api.root.add_method("ANY", integration)
        api.root.add_resource("{proxy+}").add_method("ANY", integration)
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
        CfnOutput(self, "ValidationTableName", value=self.table.table_name)
        CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id)
        CfnOutput(
            self, "UserPoolClientId", value=self.user_pool.add_client("portal-client").user_pool_client_id
        )


def _default_method_options(auth_mode: str, pool: Any) -> apigw.MethodOptions:
    """Method options shared by every route: authorization per mode.

    ``dev`` leaves the API open and the identity comes from the
    ``X-Actor-Id``/``X-Actor-Role`` headers, which is what the demo accounts of
    EF-ADM-03 need. ``cognito`` requires a signed token from the user pool.
    """
    if auth_mode != "cognito":
        return apigw.MethodOptions()
    authorizer = apigw.CognitoUserPoolsAuthorizer(
        pool.stack,
        "PortalDefaultAuthorizer",
        cognito_user_pools=[pool],
        authorizer_name="portal-cognito",
    )
    return apigw.MethodOptions(authorization_type=apigw.AuthorizationType.COGNITO, authorizer=authorizer)
