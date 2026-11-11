"""Observability stack: CloudWatch dashboard, alarms and the SNS topic.

Implements ENF-OBS-01: every load is supervised and an alarm fires on a
failure. The alarms cover the nightly load, the classification, the API of the
portal and the Athena recalculation.
"""

from __future__ import annotations

from typing import Any

from aws_cdk import CfnOutput, Duration
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as sns_subscriptions
from common import MargeStack

__all__ = ["ObservabilityStack"]


class ObservabilityStack(MargeStack):
    """CloudWatch dashboard, alarms on the failures and their notifications."""

    def __init__(
        self,
        scope: Any,
        construct_id: str,
        *,
        environment: str = "dev",
        alarm_email: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, environment=environment, **kwargs)
        self.topic = self._create_topic(alarm_email)
        self.dashboard = self._create_dashboard()
        self.alarms = self._create_alarms()
        self._outputs()

    def _create_topic(self, alarm_email: str) -> sns.Topic:
        """Create the topic that carries the alarms."""
        topic = sns.Topic(
            self,
            "AlarmTopic",
            topic_name=f"{self.qualifier}-alarms",
            display_name="Marge alarms",
        )
        if alarm_email:
            topic.add_subscription(sns_subscriptions.EmailSubscription(alarm_email))
        return topic

    def _create_dashboard(self) -> cloudwatch.Dashboard:
        """Create the supervision dashboard of the nightly pipeline."""
        return cloudwatch.Dashboard(
            self,
            "MargeDashboard",
            dashboard_name=f"{self.qualifier}-supervision",
            default_interval=Duration.hours(1),
        )

    def _create_alarms(self) -> list[cloudwatch.Alarm]:
        """Create the alarms of ENF-OBS-01 on the failures of the pipeline."""
        return [
            self._alarm(
                "LoadFailureAlarm",
                "The nightly load failed",
                "Errors",
                1,
                "Sum",
            ),
            self._alarm(
                "ClassificationFailureAlarm",
                "The classification of the work failed",
                "Errors",
                1,
                "Sum",
            ),
            self._alarm(
                "ApiFailureAlarm",
                "The validation portal API returned errors",
                "5XXError",
                5,
                "Sum",
            ),
            self._alarm(
                "RecalculationDurationAlarm",
                "The recalculation took longer than 30 minutes",
                "Duration",
                30,
                "Average",
            ),
        ]

    def _alarm(
        self,
        construct_id: str,
        description: str,
        metric: str,
        threshold: float,
        statistic: str,
    ) -> cloudwatch.Alarm:
        """Create one alarm and route it to the topic."""
        alarm = cloudwatch.Alarm(
            self,
            construct_id,
            alarm_description=description,
            metric=cloudwatch.Metric(
                namespace="Marge",
                metric_name=metric,
                statistic=statistic,
                period=Duration.minutes(5),
            ),
            threshold=threshold,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        alarm.add_alarm_action(cw_actions.SnsAction(self.topic))
        return alarm

    def _outputs(self) -> None:
        """Expose the topic the on-call rotation subscribes to."""
        CfnOutput(self, "AlarmTopicArn", value=self.topic.topic_arn)
        CfnOutput(self, "DashboardName", value=f"{self.qualifier}-supervision")
