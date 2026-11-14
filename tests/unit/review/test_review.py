"""Monthly review tests: Annex E template, figures, narration guard (EF-REV-01..03)."""

from __future__ import annotations

from decimal import Decimal

from tests.fakes.builders import golden_inputs
from tests.fakes.fake_model import ScriptedModel
from tests.fakes.fake_store import FakeStore

from marge.calc import compute_margin_month
from marge.domain import HoursSummary, Month, Settings
from marge.review import build_review_inputs, narrate_review, render_review, section_titles
from marge.review.narrate import unknown_figures


def _store_with_october() -> FakeStore:
    store = FakeStore()
    inputs = golden_inputs()
    store.upsert_clients([inputs.client])
    store.save_contract(inputs.contract)
    store.save_rates(list(inputs.rates))
    store.save_tooling_costs(list(inputs.tooling_costs))
    store.save_aws_costs(list(inputs.aws_costs))
    store.save_interventions(list(inputs.interventions))
    for classification in inputs.classifications:
        store.save_classification(classification)
    store.save_margin_months([compute_margin_month(inputs, Settings())])
    store.save_hours_summaries(
        [
            HoursSummary(
                client_id="c-001",
                month=Month.parse("2026-10"),
                included_quota=Decimal("50"),
                consumed_hours=Decimal("46"),
                out_of_scope_validated_hours=Decimal("9"),
                contract_hour_rate=Decimal("110"),
            )
        ]
    )
    return store


def test_review_contains_every_annex_e_section() -> None:
    store = _store_with_october()
    text = render_review(build_review_inputs(store, Month.parse("2026-10"), Settings()), Settings())
    for title in section_titles():
        assert title.split(".")[1].strip()[:12].lower() in text.lower()


def test_review_figures_match_the_calculation() -> None:
    """R14 — the review shows the same figures as the dashboards."""
    store = _store_with_october()
    inputs = build_review_inputs(store, Month.parse("2026-10"), Settings())
    assert inputs.total_margin == Decimal("895.00")
    assert inputs.total_margin_rate == Decimal("0.1937")
    text = render_review(inputs, Settings())
    assert "895.00 EUR" in text
    assert "19.4 %" in text


def test_review_reports_unbilled_hours_and_value() -> None:
    store = _store_with_october()
    inputs = build_review_inputs(store, Month.parse("2026-10"), Settings())
    assert inputs.unbilled_hours == Decimal("9.00")
    assert inputs.unbilled_value == Decimal("990.00")
    text = render_review(inputs, Settings())
    assert "9.00 h" in text
    assert "990.00 EUR" in text


def test_review_flags_a_client_below_the_threshold() -> None:
    settings = Settings(margin_threshold=Decimal("0.25"))
    store = _store_with_october()
    inputs = build_review_inputs(store, Month.parse("2026-10"), settings)
    assert [figure.client_id for figure in inputs.clients_below_threshold] == ["c-001"]
    assert "Calder Logistics" in render_review(inputs, settings)


def test_review_is_deterministic() -> None:
    store = _store_with_october()
    settings = Settings()
    first = render_review(build_review_inputs(store, Month.parse("2026-10"), settings), settings)
    second = render_review(build_review_inputs(store, Month.parse("2026-10"), settings), settings)
    assert first == second


def test_narration_is_used_when_it_invents_no_figure() -> None:
    store = _store_with_october()
    settings = Settings()
    inputs = build_review_inputs(store, Month.parse("2026-10"), settings)
    baseline = render_review(inputs, settings)
    model = ScriptedModel(default=baseline[:200])
    assert narrate_review(inputs, settings, model).startswith("Rentabilité")


def test_narration_is_dropped_when_it_invents_a_figure() -> None:
    store = _store_with_october()
    settings = Settings()
    inputs = build_review_inputs(store, Month.parse("2026-10"), settings)
    invented = "La marge globale est de 12 345,67 EUR, en forte hausse ce mois-ci."
    model = ScriptedModel(default=invented)
    assert narrate_review(inputs, settings, model) == render_review(inputs, settings)


def test_unknown_figures_detects_an_invented_amount() -> None:
    assert unknown_figures("marge 12 345,67 EUR", {"895.00"}) == ["12", "345.67"]
