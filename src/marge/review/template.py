"""The Annex E template, filled deterministically (EF-REV-01, EF-REV-03).

The template is the contract with the direction: same sections, same order,
same words. Only the numbers and the names change, and they all come from
``ReviewInputs`` (i.e. from the calculation, never from a model).
"""

from __future__ import annotations

from decimal import Decimal

from ..domain import Settings
from .aggregates import ReviewInputs

TEMPLATE_HEADER = """Rentabilité — {month}

1. En bref
   Marge globale : {margin} ({rate}), {variation} par rapport au mois précédent.
   Couverture des données : {coverage}.

2. Clients sous le seuil de {threshold}
{below}

3. Plus fortes variations
{variations}

4. Heures non facturées
   {hours} h repérées, soit {value}. À traiter : {todo}

5. Renouvellements dans les 90 jours
{renewals}

6. Trois décisions proposées
{decisions}
"""

EMPTY = "   Aucun."


def _percent(value: Decimal) -> str:
    return f"{(value * 100).quantize(Decimal('0.1'))} %"


def _money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'))} EUR"


def _signed_points(value: Decimal) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value.quantize(Decimal('0.1'))} point(s)"


def render_below(inputs: ReviewInputs) -> str:
    if not inputs.clients_below_threshold:
        return EMPTY
    return "\n".join(
        f"   {figure.name} — {_percent(figure.margin_rate)} — cause principale : {figure.cause}"
        for figure in inputs.clients_below_threshold
    )


def render_variations(inputs: ReviewInputs) -> str:
    if not inputs.variations:
        return EMPTY
    return "\n".join(
        f"   {variation.name} — {_signed_points(variation.delta_rate * 100)} — {variation.explanation}"
        for variation in inputs.variations
    )


def render_renewals(inputs: ReviewInputs) -> str:
    if not inputs.renewals:
        return EMPTY
    return "\n".join(
        f"   {renewal.client_id} — échéance {renewal.end_date} — "
        f"marge sur 6 mois {_percent(renewal.margin_rate_six_months)} — tendance {renewal.trend}"
        for renewal in inputs.renewals
    )


def render_decisions(inputs: ReviewInputs) -> str:
    if not inputs.decisions:
        return EMPTY
    return "\n".join(f"   {index}. {text}" for index, text in enumerate(inputs.decisions, start=1))


def render_todo(inputs: ReviewInputs) -> str:
    if not inputs.unbilled_clients:
        return "rien en attente"
    return ", ".join(f"{name} ({hours} h)" for name, hours, _ in inputs.unbilled_clients)


def render_review(inputs: ReviewInputs, settings: Settings) -> str:
    """Render the monthly review exactly as Annex E prescribes."""
    return TEMPLATE_HEADER.format(
        month=inputs.month,
        margin=_money(inputs.total_margin),
        rate=_percent(inputs.total_margin_rate),
        variation=_signed_points(inputs.margin_variation_points),
        coverage=f"{inputs.coverage_percent} %",
        threshold=_percent(settings.margin_threshold),
        below=render_below(inputs),
        variations=render_variations(inputs),
        hours=inputs.unbilled_hours.quantize(Decimal("0.01")),
        value=_money(inputs.unbilled_value),
        todo=render_todo(inputs),
        renewals=render_renewals(inputs),
        decisions=render_decisions(inputs),
    )


def section_titles() -> tuple[str, ...]:
    """The six sections, in order: used by the tests and by the flow."""
    return (
        "1. En bref",
        "2. Clients sous le seuil",
        "3. Plus fortes variations",
        "4. Heures non facturées",
        "5. Renouvellements dans les 90 jours",
        "6. Trois décisions proposées",
    )
