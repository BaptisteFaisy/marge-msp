"""The chat agent instructions, knowledge and reference questions (EF-AGT-01..03)."""

from __future__ import annotations

import pytest

from marge.quicksight import AGENT, DASHBOARD_IDS
from marge.quicksight.agent import AGENT_EXAMPLE_IDS


def test_agent_is_declared_in_english() -> None:
    assert AGENT.language == "en"
    assert AGENT.name
    assert AGENT.description


def test_agent_covers_the_three_requirements() -> None:
    assert "EF-AGT-01" in AGENT.requirement
    assert "EF-AGT-02" in AGENT.requirement
    assert "EF-AGT-03" in AGENT.requirement


def test_agent_has_instructions() -> None:
    assert AGENT.instructions
    for instruction in AGENT.instructions:
        assert instruction
        assert instruction[0].isupper()


def test_agent_instruction_forbids_inventing_a_number() -> None:
    """ENF-IA-01: the agent never estimates a figure."""
    joined = " ".join((*AGENT.instructions, *AGENT.rules)).lower()
    assert "never estimate" in joined
    assert "never computes a figure" in joined


def test_agent_instruction_requires_the_period_and_the_client() -> None:
    joined = " ".join(AGENT.instructions).lower()
    assert "period" in joined
    assert "client" in joined


def test_agent_instruction_requires_the_dashboard_link() -> None:
    joined = " ".join(AGENT.instructions).lower()
    assert "dashboard" in joined
    assert "ef-tdb-01" in joined


def test_agent_instruction_requires_the_clause_on_a_contract() -> None:
    joined = " ".join(AGENT.instructions).lower()
    assert "clause" in joined


def test_agent_instruction_says_when_a_value_is_an_estimate() -> None:
    joined = " ".join(AGENT.instructions).lower()
    assert "estimate" in joined


def test_agent_knowledge_is_the_topic_and_the_contracts() -> None:
    joined = " ".join(AGENT.knowledge).lower()
    assert "topic" in joined
    assert "contract" in joined


def test_agent_exposes_the_three_mcp_actions() -> None:
    joined = " ".join(AGENT.actions)
    assert "create_renegotiation_task" in joined
    assert "draft_extra_billing_proposal" in joined
    assert "get_margin_breakdown" in joined


def test_agent_has_the_five_example_questions() -> None:
    assert len(AGENT.examples) == 5
    assert AGENT_EXAMPLE_IDS == ("EX-01", "EX-02", "EX-03", "EX-04", "EX-05")


@pytest.mark.parametrize("example", AGENT.examples, ids=AGENT_EXAMPLE_IDS)
def test_every_example_states_its_expected_answer(example) -> None:
    assert example.question
    assert example.expected_answer
    assert example.dashboard in DASHBOARD_IDS
    assert example.must_cite


def test_examples_cover_the_five_questions_of_the_specification() -> None:
    """Chapter 14.5: margin below threshold, margin drop, out-of-scope hours,
    contract clause, renewals within 90 days."""
    questions = " ".join(example.question.lower() for example in AGENT.examples)
    assert "20%" in questions
    assert "drop in october" in questions
    assert "out-of-scope" in questions
    assert "contract" in questions
    assert "90 days" in questions


def test_no_example_quotes_a_computed_amount() -> None:
    """The expected answers describe the shape of the reply, not a computed figure."""
    for example in AGENT.examples:
        assert "EUR" not in example.expected_answer
        assert "€" not in example.expected_answer


def test_expected_answers_never_contain_a_margin_figure() -> None:
    """The agent must read the figure from the topic, not assert one."""
    for example in AGENT.examples:
        assert "895" not in example.expected_answer
        assert "4 620" not in example.expected_answer
        assert "19.4" not in example.expected_answer
