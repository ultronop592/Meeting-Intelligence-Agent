"""Multi-Factor Confidence Scorer & Self-Consistency Agent.

Implements Step 4 of Phase 2:
1. Computes a multi-factor confidence score C in [0.05, 0.99] for each extracted
   action item and decision based on 5 calibrated signals:
   - Signal 1: Verbatim Quote Grounding Fidelity (weight 0.35)
   - Signal 2: Commitment Language Strength (weight 0.25)
   - Signal 3: Owner Attribution Status (weight 0.20)
   - Signal 4: Due Date Specificity (weight 0.10)
   - Signal 5: Participant Agreement / Acknowledgement (weight 0.10)
2. Policy thresholding:
   - Any item with confidence < 0.70 is flagged with needs_review = True.
   - High-confidence items (>= 0.70) are cleared for automated workflows.
3. Configurable Self-Consistency Check:
   - Evaluates consensus across multiple extraction/verification passes when enabled.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from langsmith import traceable

from models.schemas import ActionItem, AgentState, Decision, ExtractionOutput

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1-confidence"

# Policy dispatch threshold: below this score, items cannot be auto-dispatched
CONFIDENCE_THRESHOLD = 0.70


# Regex patterns for strong commitment language
_STRONG_COMMITMENT_PATTERNS = [
    r"\bi\s+will\b",
    r"\bi'?ll\s+(take|handle|do|send|deploy|write|fix|create|set\s+up|review|run|build)\b",
    r"\bi\s+am\s+going\s+to\b",
    r"\bleave\s+it\s+to\s+me\b",
    r"\bi\s+can\s+take\s+that\b",
    r"\bi\s+own\s+this\b",
    r"\bi'?ll\s+get\s+this\s+done\b",
]

# Regex patterns for acknowledgement/agreement in surrounding context
_AGREEMENT_PATTERNS = [
    r"\bsounds\s+good\b",
    r"\bperfect\b",
    r"\bagreed\b",
    r"\bapproved\b",
    r"\bdeal\b",
    r"\bthanks\b",
    r"\bsure\b",
    r"\bwill\s+do\b",
]


def score_commitment_language(quote: str | None) -> float:
    """Evaluates the linguistic strength of a commitment quote in [0.2, 1.0]."""
    if not quote or not quote.strip():
        return 0.20

    q_lower = quote.lower()
    for pat in _STRONG_COMMITMENT_PATTERNS:
        if re.search(pat, q_lower):
            return 1.00

    # First person statement
    if re.search(r"\bi\s+can\b|\bi'?ll\b", q_lower):
        return 0.75

    # Assigned to someone else directly ("Ravi, can you... Sure.")
    if re.search(r"\bcan\s+you\b", q_lower):
        return 0.65

    # Passive statement
    return 0.40


def score_owner_attribution(owner_status: str | None) -> float:
    """Scores owner attribution clarity in [0.2, 1.0]."""
    status = (owner_status or "stated").lower()
    if status == "stated":
        return 1.00
    if status == "inferred":
        return 0.50
    return 0.20  # "unassigned"


def score_due_date_specificity(due_date: str | None) -> float:
    """Scores due date specificity in [0.3, 1.0]."""
    if not due_date or due_date.lower() in ("unspecified", "none", "tbd", ""):
        return 0.30

    # Specific ISO-8601 date YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", due_date.strip()):
        return 1.00

    return 0.70


def score_dialogue_agreement(quote: str | None, transcript: str | None) -> float:
    """Checks if the quote is met with participant agreement in transcript context."""
    if not quote or not transcript:
        return 0.50

    q_lower = quote.lower()
    t_lower = transcript.lower()

    # Locate quote position in transcript
    idx = t_lower.find(q_lower[:min(30, len(q_lower))])
    if idx == -1:
        return 0.50

    # Inspect the subsequent ~200 characters following the quote
    following_context = t_lower[idx + len(quote) : idx + len(quote) + 200]
    for pat in _AGREEMENT_PATTERNS:
        if re.search(pat, following_context):
            return 1.00

    return 0.60


def compute_action_item_confidence(
    item: ActionItem,
    transcript: str | None = None,
) -> tuple[float, dict[str, float]]:
    """
    Computes calibrated multi-factor confidence score for an ActionItem.
    """
    # Signal 1: Grounding quote fidelity (weight 0.35)
    s1_grounding = 1.00 if (item.evidence_quote and not item.needs_review) else (0.20 if not item.evidence_quote else 0.70)
    w1 = 0.35

    # Signal 2: Commitment language strength (weight 0.25)
    s2_commitment = score_commitment_language(item.evidence_quote)
    w2 = 0.25

    # Signal 3: Owner status (weight 0.20)
    s3_owner = score_owner_attribution(item.owner_status)
    w3 = 0.20

    # Signal 4: Due date specificity (weight 0.10)
    s4_due = score_due_date_specificity(item.due_date)
    w4 = 0.10

    # Signal 5: Agreement / acknowledgment (weight 0.10)
    s5_agree = score_dialogue_agreement(item.evidence_quote, transcript)
    w5 = 0.10

    raw_score = (
        (w1 * s1_grounding)
        + (w2 * s2_commitment)
        + (w3 * s3_owner)
        + (w4 * s4_due)
        + (w5 * s5_agree)
    )

    # Clamp between 0.10 and 0.99
    final_score = round(max(0.10, min(0.99, raw_score)), 2)

    breakdown = {
        "grounding": round(s1_grounding, 2),
        "commitment": round(s2_commitment, 2),
        "owner": round(s3_owner, 2),
        "due_date": round(s4_due, 2),
        "agreement": round(s5_agree, 2),
    }

    return final_score, breakdown


def compute_decision_confidence(
    decision: Decision,
    transcript: str | None = None,
) -> tuple[float, dict[str, float]]:
    """Computes confidence score for a Decision."""
    s1_grounding = 1.00 if (decision.evidence_quote and not decision.needs_review) else (0.30 if not decision.evidence_quote else 0.70)
    s2_context = 0.90 if (decision.context and len(decision.context) > 10) else 0.50
    s3_agree = score_dialogue_agreement(decision.evidence_quote, transcript)

    raw_score = (0.50 * s1_grounding) + (0.30 * s2_context) + (0.20 * s3_agree)
    final_score = round(max(0.15, min(0.99, raw_score)), 2)

    breakdown = {
        "grounding": round(s1_grounding, 2),
        "context": round(s2_context, 2),
        "agreement": round(s3_agree, 2),
    }
    return final_score, breakdown


def evaluate_self_consistency_consensus(
    candidate_descriptions: list[str],
    run_results: list[list[str]],
    token_overlap_threshold: float = 0.50,
) -> dict[str, float]:
    """
    Computes agreement ratio across N extraction runs.
    Uses token-overlap matching to align paraphrased candidate tasks.
    Returns {desc: consensus_score in [0.0, 1.0]}.
    """
    if not run_results:
        return {d: 1.0 for d in candidate_descriptions}

    total_runs = len(run_results)
    consensus_scores: dict[str, float] = {}

    for desc in candidate_descriptions:
        desc_tokens = set(re.findall(r"\w+", desc.lower()))
        if not desc_tokens:
            consensus_scores[desc] = 0.0
            continue

        count = 0
        for run in run_results:
            matched = False
            for r in run:
                r_tokens = set(re.findall(r"\w+", r.lower()))
                if not r_tokens:
                    continue
                # Overlap ratio relative to smaller token set
                overlap = len(desc_tokens.intersection(r_tokens)) / min(len(desc_tokens), len(r_tokens))
                if overlap >= token_overlap_threshold:
                    matched = True
                    break
            if matched:
                count += 1
        consensus_scores[desc] = round(count / total_runs, 2)

    return consensus_scores


@traceable(
    name="score_confidence",
    tags=["confidence-scorer", "phase-2", PROMPT_VERSION],
    metadata={"prompt_version": PROMPT_VERSION},
)
def score_confidence(state: AgentState) -> dict:
    """
    Confidence Scorer Agent Node.
    Scores every action item and decision using multi-factor signals.
    Enforces review policy: confidence < 0.70 -> needs_review = True.
    """
    logger.info("Confidence Scorer: evaluating multi-factor item confidence")

    if not state.extraction:
        return {"confidence_summary": {"status": "skipped", "reason": "no_extraction"}}

    transcript_text = state.diarized_transcript or state.transcript or ""
    action_items = state.extraction.action_items or []
    decisions = state.extraction.decisions or []

    scored_items: list[ActionItem] = []
    scored_decisions: list[Decision] = []

    high_confidence_count = 0
    flagged_count = 0
    total_score_sum = 0.0

    for item in action_items:
        score, breakdown = compute_action_item_confidence(item, transcript=transcript_text)
        updated = item.model_copy()
        updated.confidence = score

        # Policy threshold: if score < 0.70, flag for review
        if score < CONFIDENCE_THRESHOLD:
            updated.needs_review = True
            flagged_count += 1
        else:
            high_confidence_count += 1

        total_score_sum += score
        scored_items.append(updated)

    for dec in decisions:
        score, breakdown = compute_decision_confidence(dec, transcript=transcript_text)
        updated_dec = dec.model_copy()
        updated_dec.confidence = score
        if score < CONFIDENCE_THRESHOLD:
            updated_dec.needs_review = True
        scored_decisions.append(updated_dec)

    total_items = len(scored_items)
    avg_confidence = round(total_score_sum / total_items, 2) if total_items > 0 else 1.0

    updated_extraction = ExtractionOutput(
        action_items=scored_items,
        decisions=scored_decisions,
        participants=state.extraction.participants,
        key_topics=state.extraction.key_topics,
    )

    summary = {
        "total_items_scored": total_items,
        "high_confidence_items": high_confidence_count,
        "flagged_for_review": flagged_count,
        "average_confidence": avg_confidence,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
    }

    logger.info("Confidence Scorer summary: %s", summary)

    return {
        "extraction": updated_extraction,
        "confidence_summary": summary,
        "completed_nodes": state.completed_nodes + ["score_confidence"],
    }
