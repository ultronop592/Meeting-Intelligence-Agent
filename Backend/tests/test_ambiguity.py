import pytest
from agents.ambiguity import (
    detect_due_date_ambiguity,
    detect_owner_ambiguity,
    resolve_ambiguity,
)
from models.schemas import ActionItem, AgentState, Decision, ExtractionOutput, Priority


def test_detect_owner_unassigned_general_statement():
    quote = "Someone should update the risk register before the audit."
    owner, status, is_ambiguous, reason = detect_owner_ambiguity(
        owner="Priya",  # LLM guessed Priya because she spoke last
        evidence_quote=quote,
        participants=["Priya", "Amit"],
    )
    assert owner == "Unassigned"
    assert status == "unassigned"
    assert is_ambiguous is True
    assert "without an assigned owner" in reason


def test_detect_owner_tentative_commitment():
    quote = "I can probably look at the vendor contract, no promises."
    owner, status, is_ambiguous, reason = detect_owner_ambiguity(
        owner="Amit",
        evidence_quote=quote,
        participants=["Priya", "Amit"],
    )
    assert owner == "Amit"
    assert status == "inferred"
    assert is_ambiguous is True
    assert "tentative" in reason


def test_detect_owner_stated_commitment():
    quote = "I will handle the billing service deployment by Friday."
    owner, status, is_ambiguous, reason = detect_owner_ambiguity(
        owner="Alice",
        evidence_quote=quote,
        participants=["Alice", "Bob"],
    )
    assert owner == "Alice"
    assert status == "stated"
    assert is_ambiguous is False
    assert reason is None


def test_detect_owner_not_in_participants():
    quote = "Dave should review the security architecture."
    owner, status, is_ambiguous, reason = detect_owner_ambiguity(
        owner="Dave",
        evidence_quote=quote,
        participants=["Alice", "Bob"],  # Dave not in meeting
    )
    assert status == "inferred"
    assert is_ambiguous is True
    assert "not listed among verified meeting participants" in reason


def test_detect_due_date_vague_words():
    quote = "Let's finish this soon whenever you get a chance."
    due_date, is_ambiguous, reason = detect_due_date_ambiguity(
        due_date="2026-10-31",  # LLM fabricated a specific date
        evidence_quote=quote,
    )
    assert due_date == "unspecified"
    assert is_ambiguous is True
    assert "vague timing" in reason


def test_detect_due_date_explicit_kept():
    quote = "I will deliver the report by November 15th."
    due_date, is_ambiguous, reason = detect_due_date_ambiguity(
        due_date="2026-11-15",
        evidence_quote=quote,
    )
    assert due_date == "2026-11-15"
    assert is_ambiguous is False
    assert reason is None


def test_resolve_ambiguity_node_full_pipeline():
    state = AgentState(
        transcript="Meeting transcript placeholder",
        extraction=ExtractionOutput(
            action_items=[
                ActionItem(
                    description="Update the risk register",
                    owner="Priya",
                    due_date="2026-10-30",
                    evidence_quote="Someone should also update the risk register soon.",
                    confidence=0.85,
                ),
                ActionItem(
                    description="Deploy billing container",
                    owner="Alice",
                    due_date="2026-11-01",
                    evidence_quote="I will deploy the billing container by November 1st.",
                    confidence=0.95,
                ),
            ],
            participants=["Alice", "Bob", "Priya"],
        ),
    )

    result = resolve_ambiguity(state)
    items = result["extraction"].action_items

    # First item should be marked unassigned and unspecified date
    first = items[0]
    assert first.owner == "Unassigned"
    assert first.owner_status == "unassigned"
    assert first.due_date == "unspecified"
    assert first.needs_review is True
    assert first.confidence <= 0.40

    # Second item remains stated and confirmed
    second = items[1]
    assert second.owner == "Alice"
    assert second.owner_status == "stated"
    assert second.due_date == "2026-11-01"
    assert second.needs_review is False
    assert second.confidence == 0.95

    # Summary statistics
    summary = result["ambiguity_summary"]
    assert summary["unassigned_tasks"] == 1
    assert summary["vague_date_tasks"] == 1
    assert summary["flagged_for_review"] == 1
