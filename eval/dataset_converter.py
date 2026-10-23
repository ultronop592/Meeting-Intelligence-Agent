"""
eval/dataset_converter.py — Format Converter and Ingestion Utilities for Public Corpora.

Converts:
1. Raw speaker transcripts (e.g., "Alice: Good morning...") to structured MeetingGroundTruth JSON.
2. QMSum JSON format into unified schema format.
3. Plaintext transcripts with separate action-item / decision lists into benchmark test cases.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from eval.schema import (
    MeetingGroundTruth,
    ReferenceActionItem,
    ReferenceDecision,
    ReferenceSpeakerTurn,
)


def parse_dialogue_to_speaker_turns(transcript: str, estimated_wpm: int = 150) -> List[ReferenceSpeakerTurn]:
    """
    Parses dialogue in 'Speaker Name: utterance' format into sequential ReferenceSpeakerTurns
    with estimated synthetic timestamps based on speech cadence (~150 words per minute).
    """
    turns: List[ReferenceSpeakerTurn] = []
    lines = transcript.strip().splitlines()

    current_time = 0.0
    speaker_regex = re.compile(r"^([A-Za-z0-9_\-\s]+?):\s*(.*)$")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        match = speaker_regex.match(line)
        if match:
            speaker = match.group(1).strip()
            text = match.group(2).strip()
        else:
            speaker = "UNKNOWN"
            text = line

        word_count = max(1, len(text.split()))
        duration = round((word_count / estimated_wpm) * 60, 2)
        end_time = round(current_time + duration, 2)

        turns.append(ReferenceSpeakerTurn(
            speaker=speaker,
            start=current_time,
            end=end_time,
            text=text,
        ))
        current_time = end_time

    return turns


def create_meeting_benchmark(
    meeting_id: str,
    title: str,
    transcript: str,
    action_items: Optional[List[Dict[str, Any]]] = None,
    decisions: Optional[List[Dict[str, Any]]] = None,
    summary: Optional[str] = None,
    language: str = "en",
    notes: Optional[str] = None,
) -> MeetingGroundTruth:
    """Helper to construct a complete validated MeetingGroundTruth object."""
    turns = parse_dialogue_to_speaker_turns(transcript)

    ai_objs = [
        ReferenceActionItem(
            description=item["description"],
            owner=item.get("owner"),
            due_date=item.get("due_date"),
            priority=item.get("priority", "medium"),
        )
        for item in (action_items or [])
    ]

    dec_objs = [
        ReferenceDecision(
            decision=d["decision"],
            rationale=d.get("rationale"),
        )
        for d in (decisions or [])
    ]

    return MeetingGroundTruth(
        meeting_id=meeting_id,
        title=title,
        language=language,
        reference_transcript=transcript.strip(),
        speaker_turns=turns,
        action_items=ai_objs,
        decisions=dec_objs,
        reference_summary=summary.strip() if summary else None,
        notes=notes,
    )


def convert_qmsum_sample(qmsum_entry: Dict[str, Any], meeting_id: str) -> MeetingGroundTruth:
    """Converts a standard QMSum meeting record into MeetingGroundTruth schema."""
    topic_list = qmsum_entry.get("topic_list", [])
    raw_meeting = qmsum_entry.get("meeting_transcripts", [])

    lines = []
    turns: List[ReferenceSpeakerTurn] = []
    current_time = 0.0

    for turn in raw_meeting:
        speaker = turn.get("speaker", "SPEAKER")
        utterance = turn.get("content", "").strip()
        lines.append(f"{speaker}: {utterance}")

        word_count = max(1, len(utterance.split()))
        dur = round((word_count / 150) * 60, 2)
        end_time = round(current_time + dur, 2)
        turns.append(ReferenceSpeakerTurn(
            speaker=speaker,
            start=current_time,
            end=end_time,
            text=utterance,
        ))
        current_time = end_time

    full_transcript = "\n".join(lines)
    general_query_list = qmsum_entry.get("general_query_list", [])
    summary = general_query_list[0].get("answer", "") if general_query_list else ""

    return MeetingGroundTruth(
        meeting_id=meeting_id,
        title=qmsum_entry.get("meeting_name", meeting_id),
        language="en",
        reference_transcript=full_transcript,
        speaker_turns=turns,
        action_items=[],
        decisions=[],
        reference_summary=summary,
        notes="Converted from QMSum corpus sample",
    )
