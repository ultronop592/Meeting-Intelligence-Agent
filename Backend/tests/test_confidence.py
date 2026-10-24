import pytest
from agents.confidence import (
    CONFIDENCE_THRESHOLD,
    compute_action_item_confidence,
    compute_decision_confidence,
    evaluate_self_consistency_consensus,
    score_commitment_language,
    score_confidence,
    score_due_date_specificity,
    score_owner_attribution,
)
from models.schemas import ActionItem, AgentState, Decision, ExtractionOutput, Priority


def test_score_commitment_language():
    assert score_commitment_language("I will deploy the cluster by Friday.") == 1.0
    assert score_commitment_language("I'll handle the API refactor.") == 1.0
    assert score_commitment_language("I can probably look into it.") == 0.75
    assert score_commitment_language("We should probably do this.") == 0.40
    assert score_commitment_language(None) == 0.20


def test_score_owner_attribution():
    assert score_owner_attribution("stated") == 1.0
    assert score_owner_attribution("inferred") == 0.50
    assert score_owner_attribution("unassigned") == 0.20


def test_score_due_date_specificity():
    assert score_due_date_specificity("2026-11-01") == 1.0
    assert score_due_date_specificity("Friday morning") == 0.70
    assert score_due_date_specificity("unspecified") == 0.30
    assert score_due_date_specificity(None) == 0.30


def test_compute_action_item_confidence_high():
    item = ActionItem(
        description="Deploy new billing microservice",
        owner="Ravi",
        due_date="2026-11-01",
        evidence_quote="I will deploy the new billing microservice by November 1st.",
        evidence_timestamp="00:14:32",
        needs_review=False,
        owner_status="stated",
    )
    transcript = (
        "Priya: Ravi, what about billing?\n"
        "Ravi: I will deploy the new billing microservice by November 1st.\n"
        "Priya: Sounds good, thanks."
    )
    score, breakdown = compute_action_item_confidence(item, transcript=transcript)
    assert score >= 0.85
    assert breakdown["grounding"] == 1.0
    assert breakdown["commitment"] == 1.0
    assert breakdown["owner"] == 1.0
    assert breakdown["due_date"] == 1.0
    assert breakdown["agreement"] == 1.0


def test_compute_action_item_confidence_low():
    item = ActionItem(
        description="Look into Redis caching",
        owner="Unassigned",
        due_date="unspecified",
        evidence_quote=None,
        needs_review=True,
        owner_status="unassigned",
    )
    score, breakdown = compute_action_item_confidence(item, transcript=None)
    assert score < 0.45
    assert breakdown["grounding"] == 0.2
    assert breakdown["owner"] == 0.2


def test_evaluate_self_consistency_consensus():
    candidates = ["Deploy billing service", "Update docs", "Phantom task"]
    run_1 = ["Deploy billing service", "Update docs"]
    run_2 = ["Deploy billing service", "Update API docs"]
    run_3 = ["Deploy billing service"]

    consensus = evaluate_self_consistency_consensus(candidates, [run_1, run_2, run_3])
    # "Deploy billing service" was in all 3 runs
    assert consensus["Deploy billing service"] == 1.0
    # "Update docs" was in 2 of 3 runs
    assert consensus["Update docs"] >= 0.66
    # "Phantom task" was in 0 runs
    assert consensus["Phantom task"] == 0.0


def test_score_confidence_node_execution():
    state = AgentState(
        transcript="Alice: I will fix the bug today.\nBob: Perfect.",
        extraction=ExtractionOutput(
            action_items=[
                ActionItem(
                    description="Fix the production bug",
                    owner="Alice",
                    due_date="2026-10-24",
                    evidence_quote="I will fix the bug today.",
                    owner_status="stated",
                    needs_review=False,
                ),
                ActionItem(
                    description="Redesign homepage",
                    owner="Unassigned",
                    due_date="unspecified",
                    evidence_quote=None,
                    owner_status="unassigned",
                    needs_review=True,
                ),
            ],
            decisions=[
                Decision(
                    description="Use PostgreSQL Neon for primary database",
                    context="Provides managed serverless branching and scale",
                    evidence_quote="Let's agree on PostgreSQL Neon.",
                )
            ],
        ),
    )

    result = score_confidence(state)
    items = result["extraction"].action_items

    # High confidence item
    high_item = items[0]
    assert high_item.confidence >= CONFIDENCE_THRESHOLD
    assert high_item.needs_review is False

    # Low confidence item
    low_item = items[1]
    assert low_item.confidence < CONFIDENCE_THRESHOLD
    assert low_item.needs_review is True

    # Summary
    summary = result["confidence_summary"]
    assert summary["high_confidence_items"] == 1
    assert summary["flagged_for_review"] == 1
    assert summary["confidence_threshold"] == CONFIDENCE_THRESHOLD
