import json 
import logging 
from groq import Groq, APIError, APIConnectionError, APITimeoutError, RateLimitError
from tenacity import(
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    
)

from Backend.core.congif import settings 
from Backend.models.schemas import AgentState

logger = logging.getLogger(__name__)

# constants

SUMMARY_MODEL  = "llama-3.3-70b-versatile"
PROMPT_VERSION = "v1"


# system prompt template

_SYSTEM_PROMPT_TEMPLATE = """\
You are a professional meeting analyst. Write a structured summary of the meeting.
 
You are given:
  1. The full meeting transcript
  2. Pre-extracted data: action items, decisions, participants, key topics
 
Use BOTH to write an accurate, specific, professional summary.
 
FIELD RULES:
- title:
    Specific and descriptive. Never generic like "Team Meeting" or "Weekly Sync".
    Format: "[Main Topic] — [Team or Context]"
    Example: "Q3 Product Roadmap Review — Engineering Team"
 
- short_summary:
    Exactly 2 to 3 sentences. Must answer:
    (1) What was the main topic discussed?
    (2) What key decision was made?
    (3) What is the immediate next step?
 
- detailed_summary:
    One to two full paragraphs. Cover all major discussion points,
    the reasoning behind each decision, and concrete next steps with owners.
    Write in third person, past tense. Professional tone.
 
- duration_minutes:
    Estimate from transcript word count.
    Formula: round(word_count / 130 / 5) * 5   (round to nearest 5 minutes)
    Minimum: 5. If transcript is very short, use 5.
 
Return ONLY valid JSON matching this schema. No markdown. No preamble.
 
JSON SCHEMA:
{schema}
"""


def _get_system_prompt() ->str:
    schema = MeetingSummary.model_json_schema()
    return _SYSTEM_PROMPT_TEMPLATE.format(schema=json.dumps(schema))

def _build_user_messages(state: AgentState) -> str:
     """
    Combines the transcript and extraction output into a single user message.
    Clear section headers help the LLM understand which part is raw speech
    and which part is already structured data.
    """
    
    ext = state.extraction
    
    # format action items as readable bullet points
    
    if ext and ext.action_items:
        items_text= "\n".join(
            f"  • {i.description} "
            f"(Owner: {i.owner} | Due: {i.due_date} | Priority: {i.priority.value})"
            for i in ext.action_items
        )
    else:
        items_text =  " None Identifies"
        
    # format decisions 
    if ext and ext.decisions:
        decisions_text = "\n".join(
            f"  • {d.description}" for d in ext.decisions
        )
     else:
        decisions_text = "  None identified."
 
    participants_text = (
        ", ".join(ext.participants) if ext and ext.participants else "Not identified."
    )
    topics_text = (
        ", ".join(ext.key_topics) if ext and ext.key_topics else "Not identified."
    )
 
    return f"""FULL TRANSCRIPT:
{state.transcript}
 
---
 
PRE-EXTRACTED DATA (already identified — use to inform the summary):
 
ACTION ITEMS:
{items_text}
 
DECISIONS:
{decisions_text}
 
PARTICIPANTS: {participants_text}
 
KEY TOPICS: {topics_text}
"""
 
 
# ---------------------------------------------------------------------------
# Retry wrapper
# ---------------------------------------------------------------------------
 
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
            {"role": "user",   "content": user_message},
        ],
        response_format={"type": "json_object"},
        # Slightly higher temperature than extraction —
        # summaries benefit from fluent, natural language
        temperature=0.3,
        max_tokens=2048,
    )
    return response.choices[0].message.content
 
 
# ---------------------------------------------------------------------------
# LangGraph Node 3
# ---------------------------------------------------------------------------
 
@traceable(
    name="generate_summary",
    tags=["node-3", "llm", f"prompt-{PROMPT_VERSION}"],
    metadata={"model": SUMMARY_MODEL, "prompt_version": PROMPT_VERSION},
)
def generate_summary(state: AgentState) -> dict:
    """
    LangGraph Node 3 — Generate Summary.
 
    Called by:  graph/agent_graph.py via StateGraph
    Triggered by: FastAPI POST /api/meetings/process (background task)
 
    INPUT  (reads from AgentState): transcript, extraction
    OUTPUT (writes to AgentState):  summary (MeetingSummary), completed_nodes
    """
    logger.info("Node 3 — generate_summary")
 
    # --- Guard ---------------------------------------------------------------
    if not state.transcript:
        error = "generate_summary: transcript missing — cannot generate summary."
        logger.error(error)
        return {"errors": state.errors + [error]}
 
    # We can still summarise without extraction — warn but continue
    if not state.extraction:
        logger.warning(
            "generate_summary: extraction output missing. "
            "Summarising from transcript only."
        )
 
    if not settings.groq_api_key:
        error = "GROQ_API_KEY is not set in environment."
        logger.error(error)
        return {"errors": state.errors + [error]}
 
    client        = Groq(api_key=settings.groq_api_key)
    system_prompt = _get_system_prompt()
    user_message  = _build_user_message(state)
 
    try:
        logger.info("Calling %s for summary generation...", SUMMARY_MODEL)
 
        raw_json = _call_summary_llm(client, system_prompt, user_message)
 
        if not raw_json:
            error = "Groq returned an empty response during summary generation."
            logger.error(error)
            return {"errors": state.errors + [error]}
 
        summary: MeetingSummary = MeetingSummary.model_validate_json(raw_json)
 
        logger.info(
            "Summary complete | title: '%s' | duration: %d min",
            summary.title,
            summary.duration_minutes,
        )
 
        return {
            "summary":         summary,
            "completed_nodes": state.completed_nodes + ["generate_summary"],
        }
 
    except ValidationError as e:
        error = f"Summary output failed Pydantic validation: {e}"
        logger.error(error)
        return {"errors": state.errors + [error]}
 
    except json.JSONDecodeError as e:
        error = f"LLM returned invalid JSON during summary: {e}"
        logger.error(error)
        return {"errors": state.errors + [error]}
 
    except RateLimitError:
        error = "Groq rate limit hit during summary generation."
        logger.error(error)
        return {"errors": state.errors + [error]}
 
    except APITimeoutError:
        error = "Groq timed out during summary generation."
        logger.error(error)
        return {"errors": state.errors + [error]}
 
    except APIConnectionError:
        error = "Could not connect to Groq API during summary generation."
        logger.error(error)
        return {"errors": state.errors + [error]}
 
    except APIError as e:
        error = f"Groq API error during summary: {e.status_code} — {e.message}"
        logger.error(error)
        return {"errors": state.errors + [error]}