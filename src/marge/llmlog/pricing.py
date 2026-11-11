"""Model pricing, for the cost estimate of the call log (idea 18).

Prices are the public on-demand US-east list prices in USD per million tokens,
as read on 2026-11-11. They are an *estimate* used to steer decisions (which
model, which batch size), never an invoice: the billing source of truth is the
AWS bill. Override by passing a mapping to ``estimate_cost``.
"""

from __future__ import annotations

from decimal import Decimal

USD_PER_MILLION: dict[str, tuple[Decimal, Decimal]] = {
    # model id -> (input, output)
    "eu.amazon.nova-lite-v1:0": (Decimal("0.06"), Decimal("0.24")),
    "amazon.nova-lite-v1:0": (Decimal("0.06"), Decimal("0.24")),
    "eu.amazon.nova-micro-v1:0": (Decimal("0.035"), Decimal("0.14")),
    "eu.amazon.nova-pro-v1:0": (Decimal("0.80"), Decimal("3.20")),
    "eu.anthropic.claude-3-5-haiku-20241022-v1:0": (Decimal("0.80"), Decimal("4.00")),
    "anthropic.claude-haiku-4-5-20251001-v1:0": (Decimal("1.00"), Decimal("5.00")),
}

DEFAULT_PRICE = (Decimal("1.00"), Decimal("5.00"))
"""Conservative fallback: an unknown model is costed like a mid-tier one, so
an unpriced model never looks free."""

MILLION = Decimal("1000000")


def prices_for(model_id: str) -> tuple[Decimal, Decimal]:
    """Input and output price per million tokens for a model id."""
    if model_id in USD_PER_MILLION:
        return USD_PER_MILLION[model_id]
    for known, price in USD_PER_MILLION.items():
        if known.split(".")[-1] == model_id.split(".")[-1]:
            return price
    return DEFAULT_PRICE


def estimate_cost(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    table: dict[str, tuple[Decimal, Decimal]] | None = None,
) -> Decimal:
    """Estimated USD cost of one call, rounded to six decimals."""
    source = table or USD_PER_MILLION
    price_in, price_out = source.get(model_id) or prices_for(model_id)
    cost = (Decimal(input_tokens) * price_in + Decimal(output_tokens) * price_out) / MILLION
    return cost.quantize(Decimal("0.000001"))


def estimate_tokens(text: str) -> int:
    """Rough token count when the provider does not report usage.

    Four characters per token is the usual approximation for Latin-script text;
    the caller flags the record as estimated so nobody mistakes it for a metered
    value.
    """
    return max(1, len(text or "") // 4)
