import json
import logging
import os

from groq import APIConnectionError, APIError, APITimeoutError, Groq, RateLimitError
from langsmith import traceable
from pydantic import ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from core.config import settings
from core.llm_router import llm_router
from models.schemas import AgentState, ExtractionOutput

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"


_SYSTEM_PROMPT_TEMPLATE = """\
You are an expert meeting analyst. Extract structured information from the transcript.

Return ONLY valid JSON that matches this schema:
{schema}
"""


def _get_system_prompt() -> str:
    schema = ExtractionOutput.model_json_schema()
    return _SYSTEM_PROMPT_TEMPLATE.format(schema=json.dumps(schema, indent=2))


# Maximum words sent to the extraction LLM — longer transcripts are trimmed to
# avoid context-window-exceeded errors. 12 000 words ≈ 48 000 tokens, well within
# llama-3.1-70b context limits. Adjust via env var EXTRACTION_MAX_WORDS.
_EXTRACTION_MAX_WORDS = int(os.environ.get("EXTRACTION_MAX_WORDS", 12_000))


def _truncate_transcript(transcript: str, max_words: int = _EXTRACTION_MAX_WORDS) -> str:
    """Trim transcript to max_words from both ends (keep start and end)."""
    words = transcript.split()
    if len(words) <= max_words:
        return transcript
    # Keep first 80% + last 20% to preserve both context and conclusions
    keep_start = int(max_words * 0.8)
    keep_end = max_words - keep_start
    trimmed = words[:keep_start] + ["\n...[transcript trimmed for length]...\n"] + words[-keep_end:]
    return " ".join(trimmed)


@retry(
    retry=retry_if_exception_type((APIConnectionError, APITimeoutError, RateLimitError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    reraise=True,
)
def _call_extraction_llm(client: Groq, system_prompt: str, transcript: str, model: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"MEETING TRANSCRIPT:\n\n{transcript}"},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
        max_tokens=4096,
    )
    return response.choices[0].message.content or ""



@traceable(
    name="extract_information",
    tags=["node-2", "llm", f"prompt-{PROMPT_VERSION}"],
    metadata={"prompt_version": PROMPT_VERSION},
)
def extract_information(state: AgentState) -> dict:
    logger.info("Node 2 - extract_information")

    if not state.transcript:
        return {"errors": state.errors + ["extract_information: transcript missing"]}
    if not settings.groq_api_key:
        return {"errors": state.errors + ["GROQ_API_KEY is not set"]}

    # --- Multi-LLM Routing ---------------------------------------------------
    # Choose between fast 8b model and powerful 70b model based on transcript
    # word count. Threshold is configurable via LLM_ROUTING_WORD_THRESHOLD.
    transcript_text = state.diarized_transcript or state.transcript
    word_count = len(transcript_text.split())
    logger.info("Extraction: raw word count=%d, model routing threshold=%d", word_count, llm_router._word_threshold)
    routing = llm_router.select_model("extraction", word_count=word_count)
    selected_model = routing.model
    logger.info("Extraction: selected model=%s | reason=%s", selected_model, routing.reason)
    # -------------------------------------------------------------------------

    # Truncate very long transcripts to avoid context-window-exceeded errors
    safe_transcript = _truncate_transcript(transcript_text)
    if len(safe_transcript) < len(transcript_text):
        logger.warning(
            "Transcript truncated from %d to %d words for extraction (limit=%d)",
            word_count, _EXTRACTION_MAX_WORDS, _EXTRACTION_MAX_WORDS,
        )

    try:
        raw_json = _call_extraction_llm(
            Groq(api_key=settings.groq_api_key),
            _get_system_prompt(),
            safe_transcript,
            selected_model,
        )
        if not raw_json:
            return {"errors": state.errors + ["Groq returned an empty extraction response"]}

        extraction = ExtractionOutput.model_validate_json(raw_json)
        return {
            "extraction": extraction,
            "llm_model_used": selected_model,
            "completed_nodes": state.completed_nodes + ["extract_information"],
        }
    except ValidationError as e:
        return {"errors": state.errors + [f"Extraction validation failed: {e}"]}
    except json.JSONDecodeError as e:
        return {"errors": state.errors + [f"Invalid JSON from extraction model: {e}"]}
    except RateLimitError:
        return {"errors": state.errors + ["Groq rate limit reached during extraction"]}
    except APITimeoutError:
        return {"errors": state.errors + ["Groq timed out during extraction"]}
    except APIConnectionError:
        return {"errors": state.errors + ["Could not connect to Groq during extraction"]}
    except APIError as e:
        return {"errors": state.errors + [f"Groq API error during extraction: {e}"]}

