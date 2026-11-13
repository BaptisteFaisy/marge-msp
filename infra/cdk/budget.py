"""Cost guard rail: an AWS Budget on the demonstration account.

The account runs a handful of serverless services on synthetic data: a few
cents a month. The budget says so out loud, and the alert fires on SNS before
anything else can go wrong. AWS Budgets costs nothing (two budgets per
account).

The stack declares the budget, its SNS topic and the subscription that carries
the alert to the on-call mailbox of the demonstration.
"""

from __future__ import annotations

import os
from typing import Any

from aws_cdk import CfnOutput
from aws_cdk import aws_budgets as budgets
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as sns_subscriptions
from common import MargeStack

__all__ = ["BudgetStack"]

DEFAULT_LIMIT = os.environ.get("MARGE_BUDGET_LIMIT", "5")
"""Monthly budget in USD. The account must stay far below it."""


class BudgetStack(MargeStack):
    """One budget, one alert, one topic."""

    def __init__(
        self,
        scope: Any,
        construct_id: str,
        *,
        environment: str = "dev",
        alarm_email: str = "",
        limit_usd: str = DEFAULT_LIMIT,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, environment=environment, **kwargs)
        self.topic = self._create_topic(alarm_email)
        self.budget = self._create_budget(limit_usd)

    def _create_topic(self, alarm_email: str) -> sns.Topic:
        """The topic that carries the budget alert."""
        topic = sns.Topic(
            self,
            "BudgetTopic",
            topic_name=f"{self.qualifier}-budget",
            display_name="Marge budget alerts",
        )
        if alarm_email:
            topic.add_subscription(sns_subscriptions.EmailSubscription(alarm_email))
        return topic

    def _create_budget(self, limit_usd: str) -> budgets.CfnBudget:
        """The budget itself, with an alert at 80 % of the limit.

        ``ACTUAL`` compares what the month really costs; the threshold is a
        percentage of the limit, so the alert moves with the limit.
        """
        return budgets.CfnBudget(
            self,
            "MonthlyBudget",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_name=f"{self.qualifier}-monthly",
                budget_type="COST",
                time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(
                    amount=float(limit_usd),
                    unit="USD",
                ),
            ),
            notifications_with_subscribers=[
                budgets.CfnBudget.NotificationWithSubscribersProperty(
                    notification=budgets.CfnBudget.NotificationProperty(
                        notification_type="ACTUAL",
                        comparison_operator="GREATER_THAN",
                        threshold=80,
                        threshold_type="PERCENTAGE",
                    ),
                    subscribers=[
                        budgets.CfnBudget.SubscriberProperty(
                            subscription_type="SNS",
                            address=self.topic.topic_arn,
                        )
                    ],
                )
            ],
        )

    def _outputs(self) -> None:
        CfnOutput(self, "BudgetTopicArn", value=self.topic.topic_arn)
        CfnOutput(self, "BudgetName", value=f"{self.qualifier}-monthly")
        CfnOutput(self, "BudgetLimitUsd", value=DEFAULT_LIMIT)
