"""Evidence-Checking Verifier Agent.

Implements the verification loop for Phase 2:
1. For every candidate action item and decision, queries the LLM for a direct supporting
   verbatim quote, speaker, and timestamp from the meeting transcript.
2. Performs strict PROGRAMMATIC verification of the quote against the actual transcript.
   Does not trust the LLM blindly: fabricated or hallucinated quotes fail programmatic
   substring/fuzzy matching and are flagged for human review with a reduced confidence.
3. Attaches evidence quotes and approximate timestamps to each verified item.
"""
from __future__ import annotations

import difflib
import json
import logging
import os
import re
from typing import Any, Optional

from groq import APIConnectionError, APIError, APITimeoutError, Groq, RateLimitError
from langsmith import traceable
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from core.config import settings
from core.llm_router import execute_with_llm_fallback, llm_router
from models.schemas import ActionItem, AgentState, Decision, ExtractionOutput

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1-verifier"


# =============================================================================
# 1. VERIFIER PROMPT & SCHEMAS
# =============================================================================

class VerifiedItemCandidate(BaseModel):
    index: int = Field(..., description="0-based index of the item in the candidate list.")
    supported: bool = Field(..., description="True if a direct verbatim quote exists in the transcript.")
    quote: Optional[str] = Field(default=None, description="Exact sentence/quote from transcript supporting this item.")
    speaker: Optional[str] = Field(default=None, description="Name or speaker label of who said it.")
    timestamp: Optional[str] = Field(default=None, description="Approximate time (e.g. '00:14:32' or 'MM:SS') if available.")
    reasoning: Optional[str] = Field(default=None, description="Brief explanation of why this item is or isn't supported.")


class VerificationResponse(BaseModel):
    action_items_verification: list[VerifiedItemCandidate] = Field(default_factory=list)
    decisions_verification: list[VerifiedItemCandidate] = Field(default_factory=list)


_VERIFIER_SYSTEM_PROMPT = """\
You are an expert, meticulous fact-checker and evidence verifier for corporate meetings.
Your job is to examine proposed action items and decisions against the meeting transcript.

CRITICAL INSTRUCTIONS:
1. Every item MUST have a real, verbatim quote directly from the transcript.
2. Do NOT invent, paraphrase, or hallucinate quotes. If the speaker never explicitly agreed
   or made a decision, mark "supported": false and leave "quote": null.
3. Distinguish between hypothetical musings ("maybe we could look at caching") and actual
   commitments or decisions ("I will implement caching by Friday").
4. Return ONLY valid JSON matching this schema:
{schema}
"""


# =============================================================================
# 2. PROGRAMMATIC QUOTE GROUNDING (DO NOT BLINDLY TRUST LLM QUOTES)
# =============================================================================

def normalize_text_for_matching(text: str) -> str:
    """Lowercases, strips punctuation, and collapses whitespace."""
    if not text:
        return ""
    # Remove punctuation except letters, digits, and basic whitespace
    cleaned = re.sub(r"[^\w\s]", " ", text.lower(), flags=re.UNICODE)
    return " ".join(cleaned.split())


def check_quote_in_transcript(
    quote: str | None,
    transcript: str,
    threshold: float = 0.65,
) -> tuple[bool, float, str]:
    """
    Programmatically verifies if a quote exists in the transcript.

    Returns:
      (is_grounded, match_score, matched_context)
    """
    if not quote or not quote.strip() or not transcript or not transcript.strip():
        return False, 0.0, ""

    norm_quote = normalize_text_for_matching(quote)
    norm_transcript = normalize_text_for_matching(transcript)

    if not norm_quote:
        return False, 0.0, ""

    quote_tokens = norm_quote.split()
    # A standalone quote with fewer than 4 words or 15 chars is too trivial to be meaningful evidence
    if len(quote_tokens) < 4 or len(norm_quote) < 15:
        return False, 0.0, ""

    # Fast path: exact normalized substring
    if norm_quote in norm_transcript:
        return True, 1.0, quote.strip()

    # Token overlap / containment check
    transcript_tokens = norm_transcript.split()
    quote_token_set = set(quote_tokens)
    window_size = min(len(quote_tokens) + 4, len(transcript_tokens))

    best_ratio = 0.0
    best_window = ""

    # Check transcript lines first (fast & natural boundary)
    for line in transcript.splitlines():
        norm_line = normalize_text_for_matching(line)
        if not norm_line:
            continue
        line_tokens = norm_line.split()
        if not line_tokens:
            continue

        # Jaccard overlap on token sets
        overlap = len(quote_token_set.intersection(line_tokens)) / len(quote_token_set)
        if overlap > best_ratio:
            best_ratio = overlap
            best_window = line.strip()

        # Difflib sequence similarity on lines containing shared tokens
        if overlap >= 0.4:
            seq_ratio = difflib.SequenceMatcher(None, norm_quote, norm_line).ratio()
            if seq_ratio > best_ratio:
                best_ratio = seq_ratio
                best_window = line.strip()

    # Sliding window if line-level didn't cross threshold
    if best_ratio < threshold and len(transcript_tokens) >= len(quote_tokens):
        step = max(1, len(quote_tokens) // 2)
        for i in range(0, len(transcript_tokens) - len(quote_tokens) + 1, step):
            window_slice = transcript_tokens[i : i + window_size]
            slice_set = set(window_slice)
            overlap = len(quote_token_set.intersection(slice_set)) / len(quote_token_set)
            if overlap > best_ratio:
                best_ratio = overlap
                best_window = " ".join(window_slice)
                if best_ratio >= 0.90:
                    break

    is_grounded = best_ratio >= threshold
    return is_grounded, round(best_ratio, 3), best_window


def find_quote_timestamp(
    quote: str,
    speaker_segments: list[dict] | None = None,
    transcript_words: list[dict] | None = None,
) -> Optional[str]:
    """Finds the timestamp of a quote from speaker segments or word-level timings."""
    if not quote or not quote.strip():
        return None

    norm_quote = normalize_text_for_matching(quote)
    quote_tokens = norm_quote.split()
    if not quote_tokens:
        return None

    # Check speaker segments (e.g. from diarization)
    if speaker_segments:
        best_seg = None
        best_overlap = 0.0
        quote_token_set = set(quote_tokens)

        for seg in speaker_segments:
            seg_text = seg.get("text", "")
            if not seg_text:
                continue
            norm_seg = normalize_text_for_matching(seg_text)
            seg_tokens = norm_seg.split()
            overlap = len(quote_token_set.intersection(seg_tokens)) / len(quote_token_set)
            if overlap > best_overlap:
                best_overlap = overlap
                best_seg = seg

        if best_seg and best_overlap >= 0.4:
            start_sec = best_seg.get("start", 0.0)
            mins = int(start_sec // 60)
            secs = int(start_sec % 60)
            return f"{mins:02d}:{secs:02d}"

    return None


# =============================================================================
# 3. VERIFIER LLM INVOCATION
# =============================================================================

@retry(
    retry=retry_if_exception_type((APIConnectionError, APITimeoutError, RateLimitError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=6),
    reraise=True,
)
def _call_verifier_llm(client: Groq, system_prompt: str, user_content: str, model: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
        max_tokens=3072,
    )
    return response.choices[0].message.content or ""


# =============================================================================
# 4. MAIN VERIFICATION FUNCTION (LANGGRAPH NODE)
# =============================================================================

@traceable(
    name="verify_extractions",
    tags=["verifier", "phase-2", PROMPT_VERSION],
    metadata={"prompt_version": PROMPT_VERSION},
)
def verify_extractions(state: AgentState) -> dict:
    """
    Verification Agent Node.
    Takes candidate action items & decisions, locates verbatim quotes,
    performs programmatic ground-truth verification against transcript,
    and updates items with quotes, timestamps, confidence, and review flags.
    """
    logger.info("Verifier Agent: starting evidence verification")

    if not state.extraction:
        logger.warning("Verifier Agent: state.extraction missing, skipping verification")
        return {"verification_summary": {"status": "skipped", "reason": "no_extraction"}}

    transcript_text = state.diarized_transcript or state.transcript or ""
    if not transcript_text.strip():
        logger.warning("Verifier Agent: transcript empty, skipping verification")
        return {"verification_summary": {"status": "skipped", "reason": "empty_transcript"}}

    candidate_items = state.extraction.action_items or []
    candidate_decisions = state.extraction.decisions or []

    if not candidate_items and not candidate_decisions:
        return {
            "verification_summary": {
                "total_action_items": 0,
                "verified_action_items": 0,
                "total_decisions": 0,
                "verified_decisions": 0,
            }
        }

    # Prepare candidate payload for verification LLM
    items_payload = [
        {"index": idx, "description": item.description, "owner": item.owner, "due_date": item.due_date}
        for idx, item in enumerate(candidate_items)
    ]
    decisions_payload = [
        {"index": idx, "description": dec.description, "context": dec.context}
        for idx, dec in enumerate(candidate_decisions)
    ]

    schema_str = json.dumps(VerificationResponse.model_json_schema(), indent=2)
    system_prompt = _VERIFIER_SYSTEM_PROMPT.format(schema=schema_str)

    user_content = (
        f"MEETING TRANSCRIPT:\n\n{transcript_text[:18000]}\n\n"
        f"PROPOSED ACTION ITEMS:\n{json.dumps(items_payload, indent=2)}\n\n"
        f"PROPOSED DECISIONS:\n{json.dumps(decisions_payload, indent=2)}\n"
    )

    verified_actions_map: dict[int, VerifiedItemCandidate] = {}
    verified_decisions_map: dict[int, VerifiedItemCandidate] = {}

    if settings.groq_api_key:
        try:
            groq_client = Groq(api_key=settings.groq_api_key)
            # Use fast 8b model for verification to keep cost low and speed high
            selected_model = settings.llm_fast_model or "llama-3.1-8b-instant"

            raw_json, _ = execute_with_llm_fallback(
                lambda model: _call_verifier_llm(
                    groq_client,
                    system_prompt,
                    user_content,
                    model,
                ),
                primary_model=selected_model,
                fallback_model="llama-3.3-70b-versatile",
            )

            if raw_json:
                data = json.loads(raw_json)
                resp = VerificationResponse.model_validate(data)
                for item in resp.action_items_verification:
                    verified_actions_map[item.index] = item
                for dec in resp.decisions_verification:
                    verified_decisions_map[dec.index] = dec
        except Exception as exc:
            logger.warning("Verifier LLM call failed, falling back to programmatic matching: %s", exc)

    # Process Action Items with PROGRAMMATIC verification
    verified_action_items: list[ActionItem] = []
    actions_flagged = 0
    actions_verified = 0

    for idx, item in enumerate(candidate_items):
        v_info = verified_actions_map.get(idx)
        raw_quote = v_info.quote if (v_info and v_info.supported) else None
        
        # If LLM didn't find quote, attempt heuristic description search in transcript
        if not raw_quote:
            is_grounded, match_score, matched_span = check_quote_in_transcript(
                item.description, transcript_text, threshold=0.60
            )
            raw_quote = matched_span if is_grounded else None
        else:
            is_grounded, match_score, matched_span = check_quote_in_transcript(
                raw_quote, transcript_text, threshold=0.60
            )

        timestamp = None
        if v_info and v_info.timestamp:
            timestamp = v_info.timestamp
        if not timestamp and raw_quote:
            timestamp = find_quote_timestamp(
                raw_quote,
                speaker_segments=getattr(state, "speaker_segments", None),
                transcript_words=getattr(state, "transcript_words", None),
            )

        # Construct updated item
        updated_item = item.model_copy()
        if is_grounded and raw_quote:
            updated_item.evidence_quote = raw_quote
            updated_item.evidence_timestamp = timestamp or "00:00"
            updated_item.confidence = max(0.70, round(match_score, 2))
            updated_item.needs_review = False
            updated_item.verification_reasoning = (
                v_info.reasoning if v_info and v_info.reasoning
                else f"Grounded in transcript with {int(match_score * 100)}% match."
            )
            actions_verified += 1
        else:
            # Hallucinated or unsupported quote!
            updated_item.evidence_quote = None
            updated_item.evidence_timestamp = None
            updated_item.confidence = 0.35
            updated_item.needs_review = True
            updated_item.verification_reasoning = (
                "Unverified: could not find verbatim supporting quote in transcript."
            )
            actions_flagged += 1

        verified_action_items.append(updated_item)

    # Process Decisions with PROGRAMMATIC verification
    verified_decisions: list[Decision] = []
    decisions_flagged = 0
    decisions_verified = 0

    for idx, dec in enumerate(candidate_decisions):
        v_info = verified_decisions_map.get(idx)
        raw_quote = v_info.quote if (v_info and v_info.supported) else None

        if not raw_quote:
            is_grounded, match_score, matched_span = check_quote_in_transcript(
                dec.description, transcript_text, threshold=0.55
            )
            raw_quote = matched_span if is_grounded else None
        else:
            is_grounded, match_score, matched_span = check_quote_in_transcript(
                raw_quote, transcript_text, threshold=0.60
            )

        timestamp = None
        if v_info and v_info.timestamp:
            timestamp = v_info.timestamp
        if not timestamp and raw_quote:
            timestamp = find_quote_timestamp(
                raw_quote,
                speaker_segments=getattr(state, "speaker_segments", None),
                transcript_words=getattr(state, "transcript_words", None),
            )

        updated_dec = dec.model_copy()
        if is_grounded and raw_quote:
            updated_dec.evidence_quote = raw_quote
            updated_dec.evidence_timestamp = timestamp or "00:00"
            updated_dec.confidence = max(0.75, round(match_score, 2))
            updated_dec.needs_review = False
            updated_dec.verification_reasoning = (
                v_info.reasoning if v_info and v_info.reasoning
                else f"Grounded in transcript with {int(match_score * 100)}% match."
            )
            decisions_verified += 1
        else:
            updated_dec.evidence_quote = None
            updated_dec.evidence_timestamp = None
            updated_dec.confidence = 0.40
            updated_dec.needs_review = True
            updated_dec.verification_reasoning = (
                "Unverified: could not find verbatim supporting quote in transcript."
            )
            decisions_flagged += 1

        verified_decisions.append(updated_dec)

    updated_extraction = ExtractionOutput(
        action_items=verified_action_items,
        decisions=verified_decisions,
        participants=state.extraction.participants,
        key_topics=state.extraction.key_topics,
    )

    summary = {
        "total_action_items": len(verified_action_items),
        "verified_action_items": actions_verified,
        "flagged_action_items": actions_flagged,
        "total_decisions": len(verified_decisions),
        "verified_decisions": decisions_verified,
        "flagged_decisions": decisions_flagged,
    }

    logger.info("Verifier Agent summary: %s", summary)

    return {
        "extraction": updated_extraction,
        "verification_summary": summary,
        "completed_nodes": state.completed_nodes + ["verify_extractions"],
    }
