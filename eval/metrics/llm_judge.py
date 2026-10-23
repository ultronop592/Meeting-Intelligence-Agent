"""
eval/metrics/llm_judge.py — LLM-as-a-Judge for Meeting Summary Faithfulness and Coverage.

Evaluates generated meeting summaries against source transcripts:
1. Extracts discrete factual claims from the summary.
2. Checks each claim against the transcript for direct or entailed evidence.
3. Categorizes each claim: SUPPORTED, PARTIALLY_SUPPORTED, or UNSUPPORTED (Hallucination).
4. Emits a structured Faithfulness score (0.0 - 1.0) and Coverage score (0.0 - 1.0).

Supports:
- OpenRouter API (using configured OPENROUTER_API_KEY and model)
- Groq API (fallback)
- Deterministic heuristic claim validator (when API keys are absent or offline)
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ClaimVerification(BaseModel):
    claim: str
    status: str  # "SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED"
    evidence_quote: Optional[str] = None
    reasoning: Optional[str] = None


class LLMJudgeResult(BaseModel):
    faithfulness_score: float = Field(ge=0.0, le=1.0)
    coverage_score: float = Field(ge=0.0, le=1.0)
    total_claims: int = 0
    supported_claims: int = 0
    unsupported_claims: int = 0
    evaluator: str = "heuristic"
    claim_details: List[ClaimVerification] = Field(default_factory=list)
    verdict_summary: str = ""


JUDGE_PROMPT_TEMPLATE = """You are an impartial, highly rigorous evaluator for meeting intelligence systems.
Your task is to evaluate a generated meeting summary against the ground-truth verbatim meeting transcript.

Evaluate two dimensions:
1. FAITHFULNESS: Does every single claim in the summary have direct factual support in the transcript?
   - Any claim not voiced in the transcript is an UNSUPPORTED hallucination.
2. COVERAGE: Does the summary cover the main decisions, tasks, and discussion points from the meeting? (0.0 to 1.0)

TRANSCRIPT:
\"\"\"
{transcript}
\"\"\"

GENERATED SUMMARY:
\"\"\"
{summary}
\"\"\"

Output your evaluation strictly in valid JSON format matching this schema:
{{
  "faithfulness_score": <float between 0.0 and 1.0>,
  "coverage_score": <float between 0.0 and 1.0>,
  "claims": [
    {{
      "claim": "<single factual assertion from summary>",
      "status": "<SUPPORTED | UNSUPPORTED>",
      "evidence_quote": "<quote from transcript if supported, or null>",
      "reasoning": "<concise explanation>"
    }}
  ],
  "verdict_summary": "<1-2 sentence overall assessment>"
}}
"""


def _heuristic_claim_judge(transcript: str, summary: str) -> LLMJudgeResult:
    """Deterministic claim verification fallback when LLM API keys are unconfigured."""
    sentences = [s.strip() for s in re.split(r"[.!?\n]", summary) if len(s.strip()) > 10]
    if not sentences:
        return LLMJudgeResult(
            faithfulness_score=1.0,
            coverage_score=0.0,
            total_claims=0,
            supported_claims=0,
            unsupported_claims=0,
            evaluator="heuristic_rule_based",
            verdict_summary="Empty summary provided.",
        )

    clean_transcript = transcript.lower()
    trans_words = {w for w in re.sub(r"[^\w\s]", " ", clean_transcript).split() if len(w) > 3}

    claim_results: List[ClaimVerification] = []
    supported = 0

    for sentence in sentences:
        s_words = {w for w in re.sub(r"[^\w\s]", " ", sentence.lower()).split() if len(w) > 3}
        if not s_words:
            supported += 1
            claim_results.append(ClaimVerification(claim=sentence, status="SUPPORTED", reasoning="Trivial sentence"))
            continue

        supported_words = 0
        for w in s_words:
            if w in trans_words or any(tw.startswith(w[:4]) or w.startswith(tw[:4]) for tw in trans_words if len(tw) >= 4):
                supported_words += 1

        overlap = supported_words / len(s_words)
        if overlap >= 0.45:
            supported += 1
            claim_results.append(ClaimVerification(
                claim=sentence,
                status="SUPPORTED",
                reasoning=f"High semantic overlap ({overlap:.0%}) with source transcript text.",
            ))
        else:
            claim_results.append(ClaimVerification(
                claim=sentence,
                status="UNSUPPORTED",
                reasoning=f"Low semantic support ({overlap:.0%}) in transcript; potential hallucination.",
            ))

    total = len(sentences)
    faithfulness = round(supported / total, 4) if total > 0 else 1.0

    # Coverage: check if key names or commitments in transcript were addressed in summary
    transcript_nouns = {w for w in trans_words if len(w) > 5}
    summary_words = {w for w in re.sub(r"[^\w\s]", " ", summary.lower()).split()}
    coverage = round(len(transcript_nouns.intersection(summary_words)) / max(len(transcript_nouns), 1), 4)
    coverage = min(1.0, max(0.5, coverage * 2.5))  # normalize coverage scale

    return LLMJudgeResult(
        faithfulness_score=faithfulness,
        coverage_score=coverage,
        total_claims=total,
        supported_claims=supported,
        unsupported_claims=total - supported,
        evaluator="heuristic_rule_based",
        claim_details=claim_results,
        verdict_summary=f"Evaluated {total} claims: {supported} supported, {total - supported} unsupported.",
    )


def evaluate_summary_with_llm(
    transcript: str,
    summary: str,
    api_key: Optional[str] = None,
    model: str = "meta-llama/llama-3.3-70b-instruct",
) -> LLMJudgeResult:
    """
    Evaluates summary faithfulness and coverage using LLM-as-a-judge.
    Falls back gracefully to heuristic claim validation if API is unavailable.
    """
    # 1. Check for OpenRouter API key from parameters or environment
    effective_key = api_key or os.getenv("OPENROUTER_API_KEY") or os.getenv("OPERNROUTER_API_KEY") or ""

    if not effective_key:
        try:
            from core.config import settings
            effective_key = settings.effective_openrouter_api_key or settings.groq_api_key or ""
        except Exception:
            pass

    if not effective_key:
        logger.info("No LLM API key detected for judge — running heuristic claim evaluation.")
        return _heuristic_claim_judge(transcript, summary)

    # 2. Query LLM via httpx
    try:
        import httpx

        prompt = JUDGE_PROMPT_TEMPLATE.format(transcript=transcript, summary=summary)
        headers = {
            "Authorization": f"Bearer {effective_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/ultronop592/Meeting-Intelligence-Agent",
            "X-Title": "Meeting Intelligence Agent Evaluation Judge",
        }

        url = "https://openrouter.ai/api/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a precise, objective academic evaluator. Respond only in valid JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
            "max_tokens": 1200,
            "response_format": {"type": "json_object"},
        }

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)

                claims = []
                for c in parsed.get("claims", []):
                    claims.append(ClaimVerification(
                        claim=c.get("claim", ""),
                        status=c.get("status", "UNSUPPORTED"),
                        evidence_quote=c.get("evidence_quote"),
                        reasoning=c.get("reasoning"),
                    ))

                total = len(claims)
                supported = sum(1 for c in claims if c.status.upper() == "SUPPORTED")
                unsupported = total - supported

                return LLMJudgeResult(
                    faithfulness_score=float(parsed.get("faithfulness_score", supported / max(total, 1))),
                    coverage_score=float(parsed.get("coverage_score", 0.8)),
                    total_claims=total,
                    supported_claims=supported,
                    unsupported_claims=unsupported,
                    evaluator=f"llm_judge:{model}",
                    claim_details=claims,
                    verdict_summary=parsed.get("verdict_summary", "Completed LLM judge evaluation."),
                )
    except Exception as exc:
        logger.warning("LLM Judge API request failed (%s) — falling back to heuristic judge.", exc)

    return _heuristic_claim_judge(transcript, summary)
