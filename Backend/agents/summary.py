import json
import logging

from groq import APIConnectionError, APIError, APITimeoutError, Groq, RateLimitError
from langsmith import traceable
from pydantic import ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from core.config import settings
from models.schemas import AgentState, MeetingSummary

logger = logging.getLogger(__name__)

SUMMARY_MODEL = "llama-3.3-70b-versatile"
PROMPT_VERSION = "v1"

_SYSTEM_PROMPT_TEMPLATE = """\
You are a professional meeting analyst. Create a structured summary from the transcript and extracted signals.

Return ONLY valid JSON that matches this schema:
{schema}
"""


def _get_system_prompt() -> str:
    schema = MeetingSummary.model_json_schema()
    return _SYSTEM_PROMPT_TEMPLATE.format(schema=json.dumps(schema, indent=2))


def _build_user_message(state: AgentState) -> str:
    ext = state.extraction
    action_items = [f"- {i.description} (owner: {i.owner}, due: {i.due_date}, priority: {i.priority.value})" for i in (ext.action_items if ext else [])]
    decisions = [f"- {d.description}" for d in (ext.decisions if ext else [])]
    participants = ", ".join(ext.participants) if ext and ext.participants else "Not identified"
    topics = ", ".join(ext.key_topics) if ext and ext.key_topics else "Not identified"

    return (
        f"FULL TRANSCRIPT:\n{state.transcript}\n\n"
        "PRE-EXTRACTED DATA:\n"
        f"ACTION ITEMS:\n{chr(10).join(action_items) if action_items else '- None'}\n\n"
        f"DECISIONS:\n{chr(10).join(decisions) if decisions else '- None'}\n\n"
        f"PARTICIPANTS: {participants}\n"
        f"KEY TOPICS: {topics}"
    )


@retry(
    retry=retry_if_exception_type((APIConnectionError, APITimeoutError, RateLimitError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    reraise=True,
)
def _call_summary_llm(client: Groq, system_prompt: str, user_message: str) -> str:
    response = client.chat.completions.create(
        model=SUMMARY_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_object"},
        temperature=0.25,
        max_tokens=2048,
    )
    return response.choices[0].message.content or ""


@traceable(
    name="generate_summary",
    tags=["node-3", "llm", f"prompt-{PROMPT_VERSION}"],
    metadata={"model": SUMMARY_MODEL, "prompt_version": PROMPT_VERSION},
)
def generate_summary(state: AgentState) -> dict:
    logger.info("Node 3 - generate_summary")

    if not state.transcript:
        return {"errors": state.errors + ["generate_summary: transcript missing"]}
    if not settings.groq_api_key:
        return {"errors": state.errors + ["GROQ_API_KEY is not set"]}

    try:
        raw_json = _call_summary_llm(
            Groq(api_key=settings.groq_api_key),
            _get_system_prompt(),
            _build_user_message(state),
        )
        if not raw_json:
            return {"errors": state.errors + ["Groq returned an empty summary response"]}

        summary = MeetingSummary.model_validate_json(raw_json)
        return {
            "summary": summary,
            "completed_nodes": state.completed_nodes + ["generate_summary"],
        }
    except ValidationError as e:
        return {"errors": state.errors + [f"Summary validation failed: {e}"]}
    except json.JSONDecodeError as e:
        return {"errors": state.errors + [f"Invalid JSON from summary model: {e}"]}
    except RateLimitError:
        return {"errors": state.errors + ["Groq rate limit reached during summary generation"]}
    except APITimeoutError:
        return {"errors": state.errors + ["Groq timed out during summary generation"]}
    except APIConnectionError:
        return {"errors": state.errors + ["Could not connect to Groq during summary generation"]}
    except APIError as e:
        return {"errors": state.errors + [f"Groq API error during summary generation: {e}"]}
