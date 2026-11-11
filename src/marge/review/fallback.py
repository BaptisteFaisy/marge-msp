"""Delivery of the monthly review (EF-REV-02, EF-REV-03).

Two channels: the project space (an S3 object, always) and the direction's
mailbox (SES, when configured). boto3 is imported inside the methods; the
tests use the local sink instead, so nothing ever reaches the network.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain import Month


@dataclass(slots=True)
class LocalSink:
    """Records what would have been stored and sent (tests, offline demo)."""

    stored: dict[str, str] = field(default_factory=dict)
    sent: list[dict] = field(default_factory=list)

    def store(self, key: str, text: str) -> str:
        self.stored[key] = text
        return key

    def send(self, recipients: tuple[str, ...], subject: str, body: str) -> dict:
        message = {"to": list(recipients), "subject": subject, "body": body}
        self.sent.append(message)
        return message


def review_key(month: Month) -> str:
    """Where the review lives in the project space."""
    return f"reviews/{month}/profitability-review.md"


def subject_for(month: Month) -> str:
    return f"Rentabilité — {month}"


class SesMailer:
    """Sends the review with SES (boto3 imported inside the method)."""

    def __init__(self, sender: str, client=None, region: str = "eu-west-3") -> None:
        self.sender = sender
        self.region = region
        self._client = client

    def _ses(self):
        if self._client is None:
            import boto3

            self._client = boto3.client("ses", region_name=self.region)
        return self._client

    def send(self, recipients: tuple[str, ...], subject: str, body: str) -> dict:
        return self._ses().send_email(
            Source=self.sender,
            Destination={"ToAddresses": list(recipients)},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
            },
        )


class S3Archive:
    """Stores the review in the project space (S3)."""

    def __init__(self, bucket: str, client=None, region: str = "eu-west-3") -> None:
        self.bucket = bucket
        self.region = region
        self._client = client

    def _s3(self):
        if self._client is None:
            import boto3

            self._client = boto3.client("s3", region_name=self.region)
        return self._client

    def store(self, key: str, text: str) -> str:
        self._s3().put_object(
            Bucket=self.bucket, Key=key, Body=text.encode("utf-8"), ContentType="text/markdown"
        )
        return f"s3://{self.bucket}/{key}"


def publish(month: Month, text: str, recipients: tuple[str, ...], sink=None, mailer=None) -> dict:
    """Store the review in the project space and send it to the direction."""
    target = sink or LocalSink()
    key = target.store(review_key(month), text)
    delivery = (mailer or target).send(recipients, subject_for(month), text)
    return {"stored_at": key, "delivered": delivery}
