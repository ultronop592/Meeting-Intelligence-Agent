import pytest
from agents.verifier import (
    check_quote_in_transcript,
    find_quote_timestamp,
    normalize_text_for_matching,
    verify_extractions,
)
from models.schemas import ActionItem, AgentState, Decision, ExtractionOutput, Priority


def test_normalize_text_for_matching():
    raw = "  Hello,   world!! Let's build   Phase-2... "
    norm = normalize_text_for_matching(raw)
    assert norm == "hello world let s build phase 2"


def test_check_quote_exact_match():
    transcript = (
        "Alice: We need to scale our database.\n"
        "Bob: I will deploy the read replica to production by Thursday morning.\n"
        "Alice: Sounds great."
    )
    quote = "I will deploy the read replica to production by Thursday morning."
    is_grounded, score, span = check_quote_in_transcript(quote, transcript)
    assert is_grounded is True
    assert score == 1.0


def test_check_quote_with_punctuation_and_case_variations():
    transcript = "Ravi: Okay guys, I'll send over the updated budget spreadsheet to Meera today."
    quote = "I'll send over the updated budget spreadsheet to Meera today!"
    is_grounded, score, span = check_quote_in_transcript(quote, transcript)
    assert is_grounded is True
    assert score >= 0.90


def test_check_quote_hallucinated_fails():
    transcript = (
        "Alice: What should we do about auth?\n"
        "Bob: Maybe we can use OAuth2 with Supabase."
    )
    # Hallucinated quote claiming a commitment was made to write Jira tickets
    hallucinated_quote = "I will write the complete Jira tickets for auth migration before Friday."
    is_grounded, score, span = check_quote_in_transcript(hallucinated_quote, transcript)
    assert is_grounded is False
    assert score < 0.60


def test_check_quote_short_words_prevent_false_positives():
    transcript = "Alice: Yes, no problem."
    is_grounded, score, _ = check_quote_in_transcript("yes", transcript)
    assert is_grounded is False  # Too short to be reliable evidence quote alone


def test_find_quote_timestamp_from_segments():
    segments = [
        {"speaker": "SPEAKER_00", "start": 0.0, "end": 5.0, "text": "Welcome to the meeting everyone."},
        {"speaker": "SPEAKER_01", "start": 75.5, "end": 85.0, "text": "I will handle the Docker container setup by Friday."},
    ]
    quote = "I will handle the Docker container setup by Friday."
    timestamp = find_quote_timestamp(quote, speaker_segments=segments)
    # 75.5 seconds = 1 minute 15 seconds -> "01:15"
    assert timestamp == "01:15"


def test_verify_extractions_programmatic_grounding():
    transcript = (
        "Alice: Who is updating the API docs?\n"
        "Bob: I will update the API docs by Friday afternoon.\n"
        "Alice: We also decided to migrate to Postgres Neon."
    )

    state = AgentState(
        transcript=transcript,
        speaker_segments=[
            {"speaker": "SPEAKER_01", "start": 12.0, "end": 18.0, "text": "I will update the API docs by Friday afternoon."},
            {"speaker": "SPEAKER_00", "start": 20.0, "end": 25.0, "text": "We also decided to migrate to Postgres Neon."},
        ],
        extraction=ExtractionOutput(
            action_items=[
                ActionItem(
                    description="Update the API docs by Friday afternoon",
                    owner="Bob",
                    due_date="2026-10-30",
                ),
                ActionItem(
                    description="Implement Kafka event bus",  # Hallucinated, not in transcript!
                    owner="Charlie",
                    due_date="2026-11-05",
                ),
            ],
            decisions=[
                Decision(
                    description="Migrate to Postgres Neon",
                    context="Modern cloud database",
                ),
            ],
            participants=["Alice", "Bob"],
        ),
    )

    result = verify_extractions(state)
    assert "extraction" in result
    new_ext = result["extraction"]

    # First item was grounded in transcript
    grounded_item = new_ext.action_items[0]
    assert grounded_item.needs_review is False
    assert grounded_item.evidence_quote is not None
    assert "API docs" in grounded_item.evidence_quote
    assert grounded_item.evidence_timestamp == "00:12"
    assert grounded_item.confidence >= 0.70

    # Second item was a hallucination!
    hallucinated_item = new_ext.action_items[1]
    assert hallucinated_item.needs_review is True
    assert hallucinated_item.evidence_quote is None
    assert hallucinated_item.confidence <= 0.40
    assert "could not find verbatim supporting quote" in hallucinated_item.verification_reasoning

    # Decision was grounded in transcript
    grounded_dec = new_ext.decisions[0]
    assert grounded_dec.needs_review is False
    assert grounded_dec.evidence_quote is not None
    assert "Neon" in grounded_dec.evidence_quote

    # Verification summary stats
    summary = result["verification_summary"]
    assert summary["total_action_items"] == 2
    assert summary["verified_action_items"] == 1
    assert summary["flagged_action_items"] == 1
    assert summary["verified_decisions"] == 1
