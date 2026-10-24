"""Ambiguity Resolver & Participant Constrainer Agent.

Implements Step 3 of Phase 2:
1. Evaluates candidate action items for unassigned tasks or guessed owners.
   - If someone says "Someone should update the docs" -> owner="Unassigned", owner_status="unassigned", needs_review=True.
   - If commitment was tentative ("I can probably look, no promises") -> owner_status="inferred", needs_review=True.
   - Validates owners against identified meeting participants.
2. Evaluates due dates for vague commitments.
   - If someone said "soon", "someday", or relative unanchored dates, prevents LLM from guessing
     arbitrary deadlines like "next Friday" and sets due_date="unspecified", needs_review=True.
3. Preserves explicit, clear commitments as owner_status="stated" with high confidence.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from langsmith import traceable

from models.schemas import ActionItem, AgentState, Decision, ExtractionOutput

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1-ambiguity"


# Patterns indicating vague or unassigned responsibility
_UNASSIGNED_PATTERNS = [
    r"\bsomeone\s+should\b",
    r"\bsomebody\s+should\b",
    r"\bwe\s+should\s+probably\b",
    r"\bwe\s+need\s+someone\s+to\b",
    r"\bcan\s+someone\b",
    r"\banybody\s+want\s+to\b",
    r"\blet'?s\s+look\s+into\b",
    r"\bwe\s+could\s+maybe\b",
    r"\bit\s+would\s+be\s+nice\s+to\b",
]

# Patterns indicating tentative / non-committal language
_TENTATIVE_PATTERNS = [
    r"\bno\s+promises\b",
    r"\bi\s+can\s+probably\b",
    r"\bi\s+might\s+be\s+able\s+to\b",
    r"\bif\s+i\s+have\s+time\b",
    r"\bmaybe\s+i\s+can\b",
    r"\bi'?ll\s+try\s+to\b",
    r"\bnot\s+sure\s+if\s+i\s+can\b",
]

# Patterns indicating vague or non-specific due dates
_VAGUE_DATE_PATTERNS = [
    r"\bsoon\b",
    r"\blater\b",
    r"\bsomeday\b",
    r"\beventually\b",
    r"\bdown\s+the\s+road\b",
    r"\basap\b",
    r"\bwhenever\b",
    r"\bwhen\s+you\s+get\s+a\s+chance\b",
]


def detect_owner_ambiguity(
    owner: str,
    evidence_quote: str | None,
    participants: list[str] | None = None,
) -> tuple[str, str, bool, Optional[str]]:
    """
    Analyzes owner commitment and attribution.

    Returns:
      (resolved_owner, owner_status, is_ambiguous, reason)
      owner_status in {"stated", "inferred", "unassigned"}
    """
    quote = (evidence_quote or "").lower()
    owner_clean = owner.strip() if owner else ""

    # Check 1: Explicit unassigned language in quote
    for pattern in _UNASSIGNED_PATTERNS:
        if re.search(pattern, quote):
            return "Unassigned", "unassigned", True, "Task was mentioned generally without an assigned owner."

    # Check 2: Tentative non-committal language
    for pattern in _TENTATIVE_PATTERNS:
        if re.search(pattern, quote):
            return owner_clean or "Unassigned", "inferred", True, "Commitment was tentative ('no promises' or 'might be able to')."

    # Check 3: Participant alignment
    if participants and owner_clean:
        # Check case-insensitive match against participants list
        known_participants = [p.strip().lower() for p in participants if p and p.strip()]
        owner_lower = owner_clean.lower()

        # If owner is not among participants, check if first name matches
        is_known = any(
            owner_lower == p or owner_lower in p or p in owner_lower
            for p in known_participants
        )
        if not is_known and owner_clean.lower() != "unassigned":
            return (
                owner_clean,
                "inferred",
                True,
                f"Owner '{owner_clean}' is not listed among verified meeting participants.",
            )

    if not owner_clean or owner_clean.lower() == "unassigned":
        return "Unassigned", "unassigned", True, "No owner was assigned."

    return owner_clean, "stated", False, None


def detect_due_date_ambiguity(
    due_date: str | None,
    evidence_quote: str | None,
) -> tuple[str, bool, Optional[str]]:
    """
    Checks if due date is vague or unsupported.

    Returns:
      (resolved_due_date, is_ambiguous, reason)
    """
    quote = (evidence_quote or "").lower()

    # If already unspecified or empty
    if not due_date or due_date.lower() in ("unspecified", "none", "tbd", ""):
        return "unspecified", False, None

    # Check if quote contains vague timing words
    for pattern in _VAGUE_DATE_PATTERNS:
        if re.search(pattern, quote):
            # If quote says "soon" or "whenever", do not invent a specific ISO date!
            return (
                "unspecified",
                True,
                "Deadline was described with vague timing (e.g. 'soon', 'when you get a chance') rather than a specific date.",
            )

    return due_date, False, None


@traceable(
    name="resolve_ambiguity",
    tags=["ambiguity-resolver", "phase-2", PROMPT_VERSION],
    metadata={"prompt_version": PROMPT_VERSION},
)
def resolve_ambiguity(state: AgentState) -> dict:
    """
    Ambiguity Resolver Agent Node.
    Examines action items to ensure:
    - No guessed owners on general tasks
    - No guessed dates on vague requests
    - Owners are aligned with real meeting participants
    """
    logger.info("Ambiguity Resolver: checking owner and deadline ambiguity")

    if not state.extraction:
        return {"ambiguity_summary": {"status": "skipped", "reason": "no_extraction"}}

    items = state.extraction.action_items or []
    participants = state.extraction.participants or []

    resolved_items: list[ActionItem] = []
    unassigned_count = 0
    inferred_count = 0
    vague_date_count = 0

    for item in items:
        updated = item.model_copy()

        # 1. Resolve owner ambiguity
        res_owner, status, owner_ambiguous, owner_reason = detect_owner_ambiguity(
            owner=item.owner,
            evidence_quote=item.evidence_quote,
            participants=participants,
        )
        updated.owner = res_owner
        updated.owner_status = status

        # 2. Resolve due date ambiguity
        res_due, date_ambiguous, date_reason = detect_due_date_ambiguity(
            due_date=item.due_date,
            evidence_quote=item.evidence_quote,
        )
        updated.due_date = res_due

        # 3. Update flags and reasoning
        reasons = []
        if updated.verification_reasoning:
            reasons.append(updated.verification_reasoning)
        if owner_reason:
            reasons.append(owner_reason)
        if date_reason:
            reasons.append(date_reason)

        if owner_ambiguous or date_ambiguous:
            updated.needs_review = True
            # Reduce confidence for ambiguous items
            updated.confidence = min(updated.confidence, 0.55 if status == "inferred" else 0.40)

        if status == "unassigned":
            unassigned_count += 1
        elif status == "inferred":
            inferred_count += 1

        if date_ambiguous:
            vague_date_count += 1

        if reasons:
            updated.verification_reasoning = " | ".join(reasons)

        resolved_items.append(updated)

    updated_extraction = ExtractionOutput(
        action_items=resolved_items,
        decisions=state.extraction.decisions,
        participants=state.extraction.participants,
        key_topics=state.extraction.key_topics,
    )

    summary = {
        "total_items_checked": len(resolved_items),
        "unassigned_tasks": unassigned_count,
        "inferred_owner_tasks": inferred_count,
        "vague_date_tasks": vague_date_count,
        "flagged_for_review": sum(1 for it in resolved_items if it.needs_review),
    }

    logger.info("Ambiguity Resolver summary: %s", summary)

    return {
        "extraction": updated_extraction,
        "ambiguity_summary": summary,
        "completed_nodes": state.completed_nodes + ["resolve_ambiguity"],
    }
