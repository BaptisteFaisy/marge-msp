"""The seeded situations of spec 19.1 are all present in the generated data."""

from __future__ import annotations

import collections
import json
from datetime import date
from decimal import Decimal

import pytest

TODAY = date(2026, 11, 11)


def _months_of(report, client_id):
    return [f"{row.month}" for row in report.series(client_id)]


@pytest.mark.integration
def test_dataset_has_twelve_clients_over_six_months(dataset, report):
    assert len(dataset.clients) == 12
    assert report.months == ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
    assert len(report.margins) == 12 * 6
    assert 3800 <= len(dataset.interventions) <= 4300


@pytest.mark.integration
def test_two_clients_are_loss_making(report):
    """c-004 and c-009 lose money every month; nobody else complete does."""
    losing = [
        client_id
        for client_id in report.client_ids()
        if all(row.margin < 0 and row.state.value == "COMPLETE" for row in report.series(client_id))
    ]
    assert losing == ["c-004", "c-009"]


@pytest.mark.integration
def test_one_loss_making_client_has_an_abnormal_ticket_volume(dataset):
    counts = collections.Counter(item.client_id for item in dataset.interventions)
    volumes = sorted(counts.values())
    median = volumes[len(volumes) // 2]
    assert counts["c-009"] > 2 * median, "c-009 must stand out by its volume"
    assert counts["c-009"] == max(counts.values())


@pytest.mark.integration
def test_three_clients_have_repeated_out_of_scope_work(report):
    """≥ 4 out-of-scope interventions each, spread over ≥ 3 months (spec 19.1)."""
    counts = collections.Counter(
        row.client_id for row in report.classifications if row.work_class.value == "OUT_OF_SCOPE"
    )
    months = collections.defaultdict(set)
    for (client_id, month), categories in report.oos_by_category.items():
        if categories:
            months[client_id].add(month)
    repeated = sorted(
        client_id for client_id, count in counts.items() if count >= 4 and len(months[client_id]) >= 3
    )
    assert repeated == ["c-002", "c-006", "c-008"]


@pytest.mark.integration
def test_one_profitable_client_renews_in_sixty_days_with_a_falling_margin(report):
    renewals = [entry for entry in report.renewals(TODAY, 90) if entry.days_to_renewal <= 60]
    assert [entry.client_id for entry in renewals] == ["c-001"]
    entry = renewals[0]
    assert entry.days_to_renewal == 60
    assert entry.trend == "DOWN"
    rates = [row.margin_rate for row in report.series("c-001")][-3:]
    assert rates[0] > rates[1] > rates[2]
    assert all(rate > 0 for rate in rates)


@pytest.mark.integration
def test_one_contract_has_an_ambiguous_clause_labelled_uncertain(dataset, report):
    ambiguous = {row["intervention_id"] for row in dataset.labels if row["expected_class"] == "UNCERTAIN"}
    assert len(ambiguous) >= 10
    classified = {row.intervention_id: row for row in report.classifications}
    for intervention_id in ambiguous:
        assert classified[intervention_id].work_class.value == "UNCERTAIN"


@pytest.mark.integration
def test_hours_without_a_client_stay_visible(dataset, report):
    unassigned = [item for item in dataset.interventions if item.client_id == "UNASSIGNED"]
    assert len(unassigned) >= 20
    assert all(report.unassigned_hours[month] > 0 for month in report.months)


@pytest.mark.integration
def test_one_client_month_has_poor_coverage_and_is_an_estimate(report):
    estimates = [(row.client_id, str(row.month)) for row in report.margins if row.state.value == "ESTIMATE"]
    assert estimates == [("c-012", "2026-09")]
    row = report.get("c-012", "2026-09")
    assert row.coverage.value < Decimal("0.80")
    assert "coverage" in row.incomplete_reason.lower()


@pytest.mark.integration
def test_one_contract_is_not_validated_and_makes_the_margin_incomplete(dataset, report):
    unvalidated = [contract for contract in dataset.contracts if contract.status.value != "VALIDATED"]
    assert [contract.contract_id for contract in unvalidated] == ["ctr-010"]
    for month in report.months:
        assert report.get("c-010", month).state.value == "INCOMPLETE"


@pytest.mark.integration
def test_one_level_changes_rate_on_july_first(dataset):
    """R9: past months keep the rate in force, the change is dated."""
    from marge.calc import rate_in_force
    from marge.domain import Month, WorkLevel

    may = rate_in_force(dataset.rates, WorkLevel.N1, Month.parse("2026-05"))
    june = rate_in_force(dataset.rates, WorkLevel.N1, Month.parse("2026-06"))
    july = rate_in_force(dataset.rates, WorkLevel.N1, Month.parse("2026-07"))
    assert may.hourly_cost == june.hourly_cost == Decimal("50.00")
    assert july.hourly_cost == Decimal("52.50")
    assert july.effective_from == date(2026, 7, 1)


@pytest.mark.integration
def test_one_contract_has_a_second_version(dataset):
    versions = [(contract.contract_id, contract.version) for contract in dataset.contracts]
    assert ("ctr-011", 1) in versions
    assert ("ctr-011", 2) in versions
    v2 = next(contract for contract in dataset.contracts if contract.version == 2)
    assert v2.effective_from == date(2026, 8, 1)
    assert v2.fields.monthly_subscription > Decimal("3600")


@pytest.mark.integration
def test_tooling_uses_the_four_allocation_bases(dataset):
    bases = {cost.basis.value for cost in dataset.tooling}
    assert bases == {"PER_CLIENT", "PER_ACCOUNT", "PER_MANAGED_RESOURCE", "PER_LABOUR_HOUR"}


@pytest.mark.integration
def test_aws_costs_are_converted_before_the_calculation(dataset):
    """The connector converts USD to EUR with fx.csv: calc only sees one currency."""
    assert all(cost.currency == "EUR" for cost in dataset.aws_costs)
    assert set(dataset.fx) == {"2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"}
    assert all(Decimal("0.90") < rate < Decimal("0.95") for rate in dataset.fx.values())
    tooling = [cost for cost in dataset.aws_costs if cost.kind.value == "MSP_TOOLING_ACCOUNT"]
    assert tooling and all(cost.rebilled_amount == 0 for cost in tooling)


@pytest.mark.integration
def test_labels_are_150_and_never_out_of_scope_on_included_work(dataset):
    labels = dataset.labels
    assert len(labels) == 150
    classes = collections.Counter(row["expected_class"] for row in labels)
    assert classes["IN_SCOPE"] >= 60
    assert classes["OUT_OF_SCOPE"] >= 40
    assert classes["UNCERTAIN"] >= 15
    clearly = [row for row in labels if row["clearly_included"]]
    assert len(clearly) >= 60
    assert all(row["expected_class"] != "OUT_OF_SCOPE" for row in clearly)


@pytest.mark.integration
def test_reference_questions_cover_the_five_families(dataset):
    questions = dataset.questions
    assert len(questions) == 20
    assert [row["id"] for row in questions] == [f"q{index:02d}" for index in range(1, 21)]
    dashboards = {row["dashboard"] for row in questions}
    assert dashboards == {"overview", "unbilled", "contracts", "renewals"}
    assert any("clause" in row["question"].lower() for row in questions)
    assert any("renouvellent" in row["question"] for row in questions)
    assert any(row["expected_kind"] == "contract_clause" for row in questions)


@pytest.mark.integration
def test_engineer_reference_never_leaks_into_domain_objects(dataset):
    """ENF-CONF-01: the loader drops the person identifier."""
    assert not hasattr(dataset.interventions[0], "engineer_ref")
    raw = json.loads((dataset.root / "manifest.json").read_text(encoding="utf-8"))
    assert "engineer" not in json.dumps(raw).lower()
