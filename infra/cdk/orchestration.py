"""Orchestration stack: the nightly, weekly and monthly runs of spec 8.

EventBridge Scheduler starts a Step Functions state machine, which chains the
Lambda jobs in order and reports a failure on the alarm topic. The whole
journey of chapter 8 therefore runs on its own, with no operator: load and
classify the new work, recompute the margins, publish the analytical tables,
then the weekly validation queues and the monthly review.

Nothing here is a machine: Lambda, Step Functions and EventBridge Scheduler are
serverless, billed per transition and per invocation.
"""

from __future__ import annotations

from typing import Any

from aws_cdk import CfnOutput, Duration
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_scheduler as scheduler
from aws_cdk import aws_sns as sns
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as tasks
from common import MargeStack, lambda_package

__all__ = ["OrchestrationStack"]

# Le 3e jour ouvré du chapitre 14.4 n'est pas exprimable en cron : on déclenche
# le 3 du mois à 08:00 UTC, et la revue indique la période couverte. À ajuster
# si le MSP préfère un autre jour (variable de contexte MONTHLY_DAY).
NIGHTLY_CRON = "0 2 * * ? *"
WEEKLY_CRON = "0 7 ? * MON *"
MONTHLY_CRON = "0 8 3 * ? *"


class OrchestrationStack(MargeStack):
    """Schedulers, state machine and job functions of the Marge pipeline."""

    def __init__(
        self,
        scope: Any,
        construct_id: str,
        *,
        environment: str = "dev",
        table_name: str = "marge",
        curated_bucket_name: str = "",
        alarm_topic: sns.ITopic | None = None,
        monthly_cron: str = MONTHLY_CRON,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, environment=environment, **kwargs)
        self.table_name = table_name
        self.curated_bucket_name = curated_bucket_name
        self.alarm_topic = alarm_topic
        self.role = self._create_job_role()
        self.nightly = self._job("Nightly", "marge.lambdas.jobs.nightly_handler", 900)
        self.publish = self._job("Publish", "marge.lambdas.jobs.publish_handler", 600)
        self.weekly = self._job("Weekly", "marge.lambdas.jobs.weekly_handler", 300)
        self.monthly = self._job("Monthly", "marge.lambdas.jobs.monthly_handler", 300)
        self.machine = self._nightly_machine()
        self._schedules(monthly_cron)
        self._outputs()

    # ---------------------------------------------------------------- roles
    def _create_job_role(self) -> iam.Role:
        """Least-privilege role shared by the four job functions."""
        role = self.service_role(
            "JobRole",
            service="lambda.amazonaws.com",
            description="Runs the nightly, weekly and monthly Marge jobs.",
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents",
                    ],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    actions=[
                        "dynamodb:GetItem",
                        "dynamodb:PutItem",
                        "dynamodb:UpdateItem",
                        "dynamodb:Query",
                        "dynamodb:Scan",
                        "dynamodb:BatchWriteItem",
                    ],
                    resources=[f"arn:aws:dynamodb:{self.region}:{self.account}:table/{self.table_name}*"],
                ),
                iam.PolicyStatement(
                    actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                    resources=["*"],
                ),
            ],
        )
        if self.curated_bucket_name:
            role.add_to_policy(
                iam.PolicyStatement(
                    actions=["s3:PutObject", "s3:GetObject", "s3:ListBucket"],
                    resources=[
                        f"arn:aws:s3:::{self.curated_bucket_name}",
                        f"arn:aws:s3:::{self.curated_bucket_name}/*",
                    ],
                )
            )
        return role

    # ------------------------------------------------------------ functions
    def _job(self, name: str, handler: str, timeout_seconds: int) -> lambda_.Function:
        environment = {
            "MARGE_TABLE": self.table_name,
            "MARGE_REGION": self.region,
        }
        if self.curated_bucket_name:
            environment["MARGE_CURATED_BUCKET"] = self.curated_bucket_name
        return lambda_.Function(
            self,
            f"{name}Function",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler=handler,
            code=lambda_package("jobs"),
            timeout=Duration.seconds(timeout_seconds),
            memory_size=1024,
            role=self.role,
            environment=environment,
            description=f"Marge {name.lower()} job (spec 8).",
        )

    # ------------------------------------------------------- state machine
    def _nightly_machine(self) -> sfn.StateMachine:
        """classify -> recompute -> publish, with the failure reported once."""
        failed = sfn.Fail(self, "NightlyFailed", cause="NightlyRunFailed", error="MargeNightlyError")
        nightly = self._step("NightlyStep", self.nightly)
        publish = self._step("PublishStep", self.publish)
        weekly = self._step("WeeklyStep", self.weekly)
        definition = nightly.next(publish).next(weekly)
        for state in (nightly, publish, weekly):
            state.add_catch(handler=failed, result_path=sfn.JsonPath.DISCARD)
        return sfn.StateMachine(
            self,
            "NightlyStateMachine",
            state_machine_name=f"{self.qualifier}-nightly",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            timeout=Duration.hours(1),
            tracing_enabled=True,
        )

    def _step(self, name: str, function: lambda_.IFunction) -> tasks.LambdaInvoke:
        return tasks.LambdaInvoke(
            self,
            name,
            lambda_function=function,
            payload_response_only=True,
            retry_on_service_exceptions=True,
            result_path=f"$.{name}",
        )

    # ------------------------------------------------------------ schedules
    def _schedules(self, monthly_cron: str) -> None:
        self.scheduler_role = self._scheduler_role()
        self._schedule("Nightly", NIGHTLY_CRON, self.machine.state_machine_arn)
        self._schedule("Monthly", monthly_cron, self.monthly.function_arn, is_lambda=True)
        self._schedule("WeeklyReport", WEEKLY_CRON, self.weekly.function_arn, is_lambda=True)

    def _scheduler_role(self) -> iam.Role:
        """Role EventBridge Scheduler uses to start the runs."""
        role = iam.Role(
            self,
            "SchedulerRole",
            assumed_by=iam.ServicePrincipal("scheduler.amazonaws.com"),
            description="Starts the Marge nightly machine and the weekly/monthly jobs.",
        )
        role.add_to_policy(
            iam.PolicyStatement(actions=["states:StartExecution"], resources=[self.machine.state_machine_arn])
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=[self.weekly.function_arn, self.monthly.function_arn],
            )
        )
        return role

    def _schedule(self, name: str, cron: str, target_arn: str, *, is_lambda: bool = False) -> None:
        """One EventBridge Scheduler rule: the L1 resource, no L2 wrapper.

        ``schedule_expression`` is a plain ``cron(...)`` string and the target
        carries the role EventBridge assumes — both are required by
        ``CfnSchedule.TargetProperty``, which has no ``ScheduleTargetProperty``
        alias in aws-cdk-lib.
        """
        target = scheduler.CfnSchedule.TargetProperty(
            arn=target_arn,
            role_arn=self.scheduler_role.role_arn,
            input='{"source": "scheduler"}' if is_lambda else None,
        )
        scheduler.CfnSchedule(
            self,
            f"{name}Schedule",
            name=f"{self.qualifier}-{name.lower()}",
            schedule_expression=f"cron({cron})",
            schedule_expression_timezone="Europe/Paris",
            flexible_time_window=scheduler.CfnSchedule.FlexibleTimeWindowProperty(mode="OFF"),
            target=target,
            state="ENABLED",
        )

    # -------------------------------------------------------------- outputs
    def _outputs(self) -> None:
        CfnOutput(self, "NightlyStateMachineArn", value=self.machine.state_machine_arn)
        CfnOutput(self, "NightlyFunctionName", value=self.nightly.function_name)
        CfnOutput(self, "PublishFunctionName", value=self.publish.function_name)
        CfnOutput(self, "WeeklyFunctionName", value=self.weekly.function_name)
        CfnOutput(self, "MonthlyFunctionName", value=self.monthly.function_name)
        if self.alarm_topic is not None:
            self.machine.add_to_role_policy(
                iam.PolicyStatement(actions=["sns:Publish"], resources=[self.alarm_topic.topic_arn])
            )
