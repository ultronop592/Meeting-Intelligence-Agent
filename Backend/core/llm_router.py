"""
core/llm_router.py — Smart Multi-LLM Router for Meeting Intelligence Agent

WHAT IT DOES
------------
Selects the optimal Groq model for each task in the pipeline based on:
  - Task type    : "extraction" | "summary" | "query"
  - Context size : transcript word count, Q&A context character length
  - Question     : keyword complexity analysis for Q&A routing

ROUTING RULES
-------------
  Task        | Condition                                      | Model Selected
  ------------|------------------------------------------------|----------------
  extraction  | transcript < WORD_THRESHOLD words              | fast  (8b-instant)
  extraction  | transcript >= WORD_THRESHOLD words             | powerful (70b)
  summary     | Always — input is compact pre-extracted JSON   | fast  (8b-instant)
  query       | Simple keyword question (who/what/list)        | fast  (8b-instant)
  query       | Complex / analytical / long-context question   | powerful (70b)

USAGE
-----
    from core.llm_router import LLMRouter

    router = LLMRouter()

    # In extraction node:
    decision = router.select_model("extraction", word_count=len(transcript.split()))
    model_name = decision.model     # e.g. "llama-3.1-8b-instant"

    # In Q&A route:
    decision = router.select_model("query", question=question, context_length=len(context))
    model_name = decision.model
"""

import logging
from dataclasses import dataclass
from typing import Literal, Optional

from core.config import settings

logger = logging.getLogger(__name__)

TaskType = Literal["extraction", "summary", "query"]

# ---------------------------------------------------------------------------
# Simple question keywords — if the Q&A question is dominated by these,
# we can safely use the fast model without losing quality.
# ---------------------------------------------------------------------------
_SIMPLE_QUERY_KEYWORDS = frozenset({
    "who",
    "how many",
    "when",
    "where",
    "list",
    "what are",
    "participants",
    "attendees",
    "action items",
    "tasks",
    "decisions",
    "summary",
    "summarize",
    "overview",
    "title",
    "duration",
    "topics",
})

# Max context length (chars) for which we still consider a query "simple"
_SIMPLE_CONTEXT_LENGTH_CHARS = 2000


@dataclass
class LLMRoutingDecision:
    """Holds the result of a routing decision with full auditability."""

    model: str
    task_type: TaskType
    reason: str

    def __str__(self) -> str:
        return f"[LLMRouter] task={self.task_type} | model={self.model} | reason={self.reason}"


class LLMRouter:
    """
    Selects the optimal Groq model for a given task.

    Uses settings from ``core/config.py`` so thresholds can be tuned
    via environment variables without any code changes:
      LLM_FAST_MODEL                — default: llama-3.1-8b-instant
      LLM_POWERFUL_MODEL            — default: llama-3.3-70b-versatile
      LLM_ROUTING_WORD_THRESHOLD    — default: 3000 words
    """

    def __init__(self) -> None:
        self._fast    = settings.llm_fast_model
        self._powerful = settings.llm_powerful_model
        self._word_threshold = settings.llm_routing_word_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def select_model(
        self,
        task_type: TaskType,
        *,
        word_count: int = 0,
        question: Optional[str] = None,
        context_length: int = 0,
    ) -> LLMRoutingDecision:
        """
        Select the best Groq model for a task.

        Args:
            task_type       : One of "extraction", "summary", "query".
            word_count      : Number of words in the transcript (for "extraction").
            question        : The user's Q&A question text (for "query").
            context_length  : Total character length of the prompt context (for "query").

        Returns:
            LLMRoutingDecision with .model, .task_type, .reason populated.
        """
        if task_type == "extraction":
            decision = self._route_extraction(word_count)
        elif task_type == "summary":
            decision = self._route_summary()
        elif task_type == "query":
            decision = self._route_query(question or "", context_length)
        else:
            # Unknown task — default to powerful model for safety
            decision = LLMRoutingDecision(
                model=self._powerful,
                task_type=task_type,
                reason=f"unknown_task_type_defaulting_to_powerful",
            )

        logger.info(str(decision))
        return decision

    # ------------------------------------------------------------------
    # Private routing helpers
    # ------------------------------------------------------------------

    def _route_extraction(self, word_count: int) -> LLMRoutingDecision:
        """
        Route extraction based on transcript word count.
        Short transcripts are well within the 8b model's capability.
        Long transcripts with complex entity relationships need 70b.
        """
        if word_count < self._word_threshold:
            return LLMRoutingDecision(
                model=self._fast,
                task_type="extraction",
                reason=f"short_transcript ({word_count} words < {self._word_threshold} threshold)",
            )
        return LLMRoutingDecision(
            model=self._powerful,
            task_type="extraction",
            reason=f"long_transcript ({word_count} words >= {self._word_threshold} threshold)",
        )

    def _route_summary(self) -> LLMRoutingDecision:
        """
        Summary always uses the fast model.
        The summary node receives compact pre-extracted JSON (action items,
        decisions, participants, topics) — not the raw transcript — so the
        8b model has more than enough capability for high-quality output.
        """
        return LLMRoutingDecision(
            model=self._fast,
            task_type="summary",
            reason="summary_input_is_compact_preextracted_data",
        )

    def _route_query(self, question: str, context_length: int) -> LLMRoutingDecision:
        """
        Route Q&A queries by question complexity and context size.

        Simple rule: if the question is short AND contains only simple
        lookup keywords AND the context is small, use the fast model.
        Everything else gets the powerful model.
        """
        question_lower = question.lower().strip()

        # Check if question is dominated by simple keyword patterns
        is_simple_keyword = any(kw in question_lower for kw in _SIMPLE_QUERY_KEYWORDS)
        is_short_question = len(question.split()) <= 12
        is_small_context  = context_length <= _SIMPLE_CONTEXT_LENGTH_CHARS

        if is_simple_keyword and is_short_question and is_small_context:
            return LLMRoutingDecision(
                model=self._fast,
                task_type="query",
                reason="simple_keyword_query_short_context",
            )

        reason_parts = []
        if not is_simple_keyword:
            reason_parts.append("complex_question_no_simple_keywords")
        if not is_short_question:
            reason_parts.append(f"long_question ({len(question.split())} words)")
        if not is_small_context:
            reason_parts.append(f"large_context ({context_length} chars)")

        return LLMRoutingDecision(
            model=self._powerful,
            task_type="query",
            reason="|".join(reason_parts) or "analytical_query",
        )


# ---------------------------------------------------------------------------
# Module-level singleton — import and reuse this across the app
# ---------------------------------------------------------------------------
llm_router = LLMRouter()
