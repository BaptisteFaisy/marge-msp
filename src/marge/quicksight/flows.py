"""The scheduled monthly review flow (EF-REV-01..03).

A Quick scheduled flow belongs to the user who creates it (spec 14.4): the
controller creates it, on the third working day of the month, and it reads the
dashboards and the topic, writes the review of Annex E, sends it to the
direction and files it in the project space.

The fallback (EF-REV-03) is a Lambda that builds the same review from the
aggregates with Bedrock and sends it by SES, used when the scheduled flow is
not convenient.
"""

from __future__ import annotations

from .models import FlowSpec, FlowStep

__all__ = ["FLOWS", "FLOW_IDS", "flow_by_id"]

_STEPS: tuple[FlowStep, ...] = (
    FlowStep(
        order=1,
        action="read_dashboards",
        detail=(
            "Read EF-TDB-01 (margin, clients under the threshold, variations), EF-TDB-03 "
            "(unbilled hours) and EF-TDB-04 (renewals within 90 days) for the closed month."
        ),
    ),
    FlowStep(
        order=2,
        action="read_topic",
        detail=(
            "Read the topic to resolve every figure with its definition, its unit and its "
            "period, so that the review and the dashboards carry the same numbers."
        ),
    ),
    FlowStep(
        order=3,
        action="reason",
        detail=(
            "Rank the clients under the threshold, identify the strongest variations and explain "
            "each of them with the cost post that moved."
        ),
    ),
    FlowStep(
        order=4,
        action="write",
        detail=(
            "Write the review with the template of Annex E: summary, clients under the threshold, "
            "strongest variations, unbilled hours, renewals within 90 days, three decisions."
        ),
    ),
    FlowStep(
        order=5,
        action="send",
        detail="Send the review by e-mail to the direction, with the dashboard links in the body.",
    ),
    FlowStep(
        order=6,
        action="file",
        detail="File the review as a document in the Marge project space, next to the contracts.",
    ),
)

FLOWS: tuple[FlowSpec, ...] = (
    FlowSpec(
        flow_id="FLOW-MONTHLY-REVIEW",
        name="Monthly profitability review",
        requirement="EF-REV-01, EF-REV-02",
        owner="controller",
        schedule="Monthly, on the third working day of the month, at 07:00 UTC",
        sources=(
            "EF-TDB-01",
            "EF-TDB-03",
            "EF-TDB-04",
            "marge_topic",
        ),
        destinations=(
            "email:direction@marge.example (the direction)",
            "space:marge_project (the project space, next to the contracts)",
        ),
        steps=_STEPS,
        fallback=(
            "EF-REV-03: the marge.review.fallback Lambda builds the same review from the "
            "aggregates of the last closed month with Bedrock and sends it by SES to the same "
            "recipients. It is used when the scheduled flow does not fit the calendar."
        ),
        template="Annex E — monthly review template",
        description=(
            "Scheduled flow that reads the dashboards and the topic, writes the monthly review "
            "of Annex E, sends it to the direction and files it in the project space."
        ),
    ),
)

FLOW_IDS: tuple[str, ...] = tuple(flow.flow_id for flow in FLOWS)


def flow_by_id(flow_id: str) -> FlowSpec:
    """Return the flow ``flow_id`` or raise ``KeyError``."""
    for flow in FLOWS:
        if flow.flow_id == flow_id:
            return flow
    raise KeyError(f"no flow named {flow_id!r}")
