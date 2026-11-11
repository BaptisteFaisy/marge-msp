"""Tunable settings (EF-ADM-01).

Everything a controller may change without a code release lives here. Values
are the defaults of the specification; the portal exposes them read/write.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(slots=True)
class Settings:
    """Runtime knobs of the calculation and of the AI steps."""

    margin_threshold: Decimal = Decimal("0.20")
    """A client below this margin rate shows up in the monthly review."""

    coverage_floor: Decimal = Decimal("0.80")
    """Below this coverage a month is flagged as an estimate (spec 12.4)."""

    classification_confidence_threshold: Decimal = Decimal("0.75")
    """Below this confidence the class becomes UNCERTAIN (spec 13.2)."""

    min_hours_for_validation: Decimal = Decimal("0.25")
    """Out-of-scope work shorter than 15 minutes is counted, not queued."""

    match_confidence_threshold: Decimal = Decimal("0.80")
    """Below this confidence a match proposal is not auto-suggested."""

    renewal_horizon_days: int = 90
    """Renewal watch window (EF-CTR-05, EF-TDB-04)."""

    monthly_review_day_of_month: int = 3
    """Third working day: the scheduled flow runs then (spec 14.4)."""

    bedrock_inference_profile: str = "standard"
    """Latency mode accepted by Bedrock: `standard` or `optimized`.

    Spec 13.2 planned the Flex tier for the nightly batch. Flex is a pricing
    tier reached through a *flex inference profile*, not through this setting,
    and the demo account exposes none in eu-west-1 — see the note in
    ``marge.classify.bedrock`` and docs/DECISIONS.md.
    """

    classification_model_id: str = "amazon-bedrock-classifier"
    bedrock_data_automation_profile_id: str = "marge-contract-fields-v1"

    region: str = "eu-west-3"
    currency: str = "EUR"
    billing_currency: str = "USD"

    def below_margin_threshold(self, margin_rate: Decimal) -> bool:
        return margin_rate < self.margin_threshold

    def needs_validation(self, hours_spent: Decimal, is_out_of_scope: bool) -> bool:
        """Should this classification be queued for a human (spec 13.2)?

        Out-of-scope work shorter than the 15 minute floor is counted but not
        queued, so it does not drown the account manager.
        """
        if not is_out_of_scope:
            return False
        return hours_spent >= self.min_hours_for_validation
