import pytest
from pydantic import ValidationError

from models.schemas import (
    ActionItem,
    ActionItemRow,
    Decision,
    DecisionRow,
    AgentState,
    Priority,
)
from db.models import ActionItem as ActionItemModel, Decision as DecisionModel


def test_action_item_verification_fields_defaults():
    item = ActionItem(
        description="Refactor database connection pool",
        owner="Alice",
    )
    assert item.due_date == "unspecified"
    assert item.priority == Priority.medium
    assert item.evidence_quote is None
    assert item.evidence_timestamp is None
    assert item.confidence == 1.0
    assert item.needs_review is False
    assert item.owner_status == "stated"
    assert item.verification_reasoning is None


def test_action_item_with_full_verification_data():
    item = ActionItem(
        description="Deploy new billing microservice",
        owner="Ravi",
        due_date="2026-11-01",
        priority=Priority.high,
        evidence_quote="I will deploy the new billing microservice by November 1st.",
        evidence_timestamp="00:14:32",
        confidence=0.95,
        needs_review=False,
        owner_status="stated",
        verification_reasoning="Direct first-person commitment with explicit deadline.",
    )
    assert item.confidence == 0.95
    assert item.needs_review is False
    assert item.owner_status == "stated"
    assert "billing" in item.evidence_quote


def test_action_item_confidence_range_validation():
    # Value > 1.0 should fail
    with pytest.raises(ValidationError):
        ActionItem(
            description="Test task",
            owner="Alice",
            confidence=1.5,
        )

    # Value < 0.0 should fail
    with pytest.raises(ValidationError):
        ActionItem(
            description="Test task",
            owner="Alice",
            confidence=-0.1,
        )


def test_decision_verification_fields():
    dec = Decision(
        description="Migrate primary database to PostgreSQL Neon",
        context="Provides autoscaling compute and managed branching.",
        evidence_quote="Let's officially decide to migrate to Neon for branching.",
        evidence_timestamp="00:22:15",
        confidence=0.98,
        needs_review=False,
        verification_reasoning="Consensus reached among all attendees.",
    )
    assert dec.confidence == 0.98
    assert dec.needs_review is False
    assert dec.evidence_timestamp == "00:22:15"


def test_row_models_serialization():
    action_row = ActionItemRow(
        id="act-123",
        meeting_id="meet-456",
        description="Review pull request",
        owner="Bob",
        due_date="2026-10-30",
        priority=Priority.low,
        evidence_quote="Bob, take a look when you get a chance.",
        evidence_timestamp="00:05:10",
        confidence=0.75,
        needs_review=True,
        owner_status="inferred",
        verification_reasoning="Assigned by peer without explicit confirmation.",
    )
    assert action_row.confidence == 0.75
    assert action_row.needs_review is True
    assert action_row.owner_status == "inferred"

    decision_row = DecisionRow(
        id="dec-123",
        meeting_id="meet-456",
        description="Use Redis for token caching",
        context="Reduces Neon read latency",
        evidence_quote="Agreed on Redis.",
        evidence_timestamp="00:12:00",
        confidence=0.9,
        needs_review=False,
        verification_reasoning="Explicit consensus",
    )
    assert decision_row.confidence == 0.9


def test_agent_state_verification_summary():
    state = AgentState(
        transcript="Alice: I will fix this.\nBob: Sounds good.",
        verification_summary={
            "total_action_items": 1,
            "verified_count": 1,
            "flagged_for_review": 0,
            "avg_confidence": 0.95,
        },
    )
    assert state.verification_summary["verified_count"] == 1


def test_sqlalchemy_models_accept_verification_columns():
    db_item = ActionItemModel(
        meeting_id="meet-test-1",
        description="Test ORM action item",
        owner="Alice",
        due_date="2026-10-31",
        priority="medium",
        evidence_quote="Verbatim quote here",
        evidence_timestamp="00:01:23",
        confidence=0.88,
        needs_review=True,
        owner_status="stated",
        verification_reasoning="Needs confirmation on due date",
    )
    assert db_item.confidence == 0.88
    assert db_item.needs_review is True
    assert db_item.owner_status == "stated"

    db_decision = DecisionModel(
        meeting_id="meet-test-1",
        description="Test ORM decision",
        context="Test context",
        evidence_quote="Decision quote",
        evidence_timestamp="00:04:55",
        confidence=0.92,
        needs_review=False,
        verification_reasoning="Clear agreement",
    )
    assert db_decision.confidence == 0.92
    assert db_decision.evidence_timestamp == "00:04:55"
