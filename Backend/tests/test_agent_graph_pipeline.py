import pytest
from graph.agent_graph import (
    build_agent_graph,
    route_after_extraction,
    route_after_transcription,
    route_after_verification,
    verify_and_score_extractions,
)
from models.schemas import ActionItem, AgentState, Decision, ExtractionOutput, Priority


def test_build_agent_graph_has_all_five_nodes():
    graph = build_agent_graph()
    # Check that graph is compiled and has the nodes
    node_names = set(graph.nodes.keys())
    expected_nodes = {
        "transcribe_audio",
        "extract_information",
        "verify_extractions",
        "generate_summary",
        "save_to_database",
    }
    assert expected_nodes.issubset(node_names)


def test_routing_after_extraction():
    # If extraction is present, routes to verify_extractions
    state_with_extraction = AgentState(
        transcript="Test transcript",
        extraction=ExtractionOutput(action_items=[], decisions=[]),
    )
    assert route_after_extraction(state_with_extraction) == "verify_extractions"

    # If extraction is missing, routes to end
    state_empty = AgentState(transcript="Test transcript")
    assert route_after_extraction(state_empty) == "end"


def test_routing_after_verification_success():
    state = AgentState(
        transcript="Test transcript",
        extraction=ExtractionOutput(action_items=[]),
        verification_summary={
            "total_action_items": 2,
            "verified_action_items": 2,
            "flagged_action_items": 0,
        },
    )
    assert route_after_verification(state) == "generate_summary"


def test_routing_after_verification_retry_feedback():
    # If 100% of items are flagged on first pass, triggers retry_extraction
    state = AgentState(
        transcript="Test transcript",
        extraction=ExtractionOutput(
            action_items=[
                ActionItem(description="Phantom task", owner="Unknown"),
            ]
        ),
        verification_summary={
            "total_action_items": 1,
            "verified_action_items": 0,
            "flagged_action_items": 1,
        },
        verification_retry_count=0,
    )
    assert route_after_verification(state) == "retry_extraction"

    # If retry count already reached max (1), proceeds to generate_summary
    state.verification_retry_count = 1
    assert route_after_verification(state) == "generate_summary"


def test_verify_and_score_extractions_full_node():
    transcript = (
        "Alice: We need someone to update the billing microservice.\n"
        "Bob: I will update the billing microservice by November 1st.\n"
        "Alice: Perfect, sounds good.\n"
        "Alice: Someone should also check the logs sometime."
    )

    state = AgentState(
        transcript=transcript,
        extraction=ExtractionOutput(
            action_items=[
                ActionItem(
                    description="Update the billing microservice",
                    owner="Bob",
                    due_date="2026-11-01",
                ),
                ActionItem(
                    description="Check the production logs",
                    owner="Alice",
                    due_date="2026-10-31",
                ),
            ],
            participants=["Alice", "Bob"],
        ),
    )

    result = verify_and_score_extractions(state)
    assert "extraction" in result
    assert "verification_summary" in result
    assert "completed_nodes" in result
    assert "verify_extractions" in result["completed_nodes"]

    extraction = result["extraction"]
    items = extraction.action_items

    # Bob's task: verified, strong commitment, high confidence
    bobs_task = items[0]
    assert bobs_task.owner == "Bob"
    assert bobs_task.owner_status == "stated"
    assert bobs_task.evidence_quote is not None
    assert "billing microservice" in bobs_task.evidence_quote
    assert bobs_task.confidence >= 0.70
    assert bobs_task.needs_review is False

    # Second task: general statement ("Someone should... sometime")
    unassigned_task = items[1]
    assert unassigned_task.owner == "Unassigned"
    assert unassigned_task.owner_status == "unassigned"
    assert unassigned_task.due_date == "unspecified"
    assert unassigned_task.needs_review is True
    assert unassigned_task.confidence < 0.70
