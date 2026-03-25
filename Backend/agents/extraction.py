import json
import logging
from xml.dom import Node 

from groq import Groq, APIError, APIConnectionError, APITimeoutError, RateLimitError
from langsmith import traceable
from pydantic import ValidationError
from tenacity import (
    retry,
    stop_after_attempt,
    stop_after_attemtp,
    wait_exponential,
    retry_if_exception_type,
    
)

from Backend.core.config import settings
from Backend.models.schemas import Agentstate, ExtractionResultOutput

logger =  logging.getLogger(__name__)

#// constants

EXTRACTION_MODEL = "llama-3.3-70b-versatile"
PROMPT_VERSION = "v1"

# // System prompt template

_SYSTEM_PROMPT_TEMPLATE = """\
    You are an expert meeting analyst. Your job is to extract structured information \
from the meeting transcript provided by the user.
 
Extract ALL of the following:
 
1. ACTION ITEMS — Every concrete task discussed. Must have:
   - A specific person's full name as owner (never "the team" or "everyone")
   - A due date in YYYY-MM-DD format
   - A priority: exactly "high", "medium", or "low"
 
2. DECISIONS — Every conclusion or agreement reached in the meeting.
 
3. PARTICIPANTS — Full names of everyone who spoke or was mentioned as present.
 
4. KEY TOPICS — 2 to 6 short noun phrases summarising what was discussed.
   Example: ["Q3 roadmap", "hiring plan", "auth refactor"]
 
STRICT RULES:
- If a due date is stated ("by Friday", "end of month", "next sprint"), \
convert it to a real YYYY-MM-DD date relative to today.
- If no due date is mentioned, default to 14 days from today.
- Return ONLY valid JSON. No markdown fences. No explanation. No preamble.
- Every string value must be in English.
 
Return JSON matching this exact schema:
{schema}
"""

def _get_system_prompt() -> str:
    """
    Builds the system prompt with the live ExtractionOutput JSON schema embedded.
    Called fresh on every invocation so it always reflects the current schema.
    """
    schema =  ExtractionResultOutput.model_json_schema()
    return _SYSTEM_PROMPT_TEMPLATE.format(schema=json.dumps(schema, indent=2))


# retry : only on transient network / rate limit error

@retry(
    retry = retry_if_exception_type((APIConnectionError, APITimeoutError, RateLimitError)),
    stop = stop_after_attempt(3),
    wait = wait_exponential(multiplier=1, min=2, max=8),
    reraise = True,
)

def _call_extraction_llm(client: Groq, system_prompt: str, transcript: str)-> str:
    """
    Calls the Groq chat completion API with retry.
    Returns raw JSON string from the LLM.
    """
    
    response =  client.chat.completions.create(
        model =  EXTRACTION_MODEL,
        messages= [
             {"role": "system", "content": system_prompt},
            {"role": "user",   "content": f"MEETING TRANSCRIPT:\n\n{transcript}"},
        ],
        response_format = {"type": "json_object"},
        temperature=0.1,
        max_tokens = 4100,
        
    )
    return response.choices[0].message.content

#// langGraph Node 2

@traceable(
    name =  "extract_information",
    tags = ["node-2", "llm", f"prompt-{PROMPT_VERSION}"],
    metadata = {"model": EXTRACTION_MODEL, "prompt_version": PROMPT_VERSION},
)

def extract_information(agent_state: Agentstate) -> dict:
    """"
    LangGraph Node 2 — Extract Information.
 
    Called by:  graph/agent_graph.py via StateGraph
    Triggered by: FastAPI POST /api/meetings/process (background task)
 
    INPUT  (reads from AgentState): transcript
    OUTPUT (writes to AgentState):  extraction (ExtractionOutput), completed_nodes
    """
    logger.info("Node 2 — extract_information | transcript: %d chars", len(state.transcript or ""))
 
    # --- Guard clauses ------------------------------------------------------
    
    if not state.transcript:
        error = "extract_information: transcript missing — Node 1 may have failed."
        logger.error(error)
        return {"errors": state.errors + [error]}
 
    if not settings.groq_api_key:
        error = "GROQ_API_KEY is not set in environment."
        logger.error(error)
        return {"errors": state.errors + [error]}
 
    client        = Groq(api_key=settings.groq_api_key)
    system_prompt = _get_system_prompt()
 
    try:
        logger.info("Calling %s for extraction...", EXTRACTION_MODEL)
 
        raw_json = _call_extraction_llm(client, system_prompt, state.transcript)
 
        if not raw_json:
            error = "Groq returned an empty response during extraction."
            logger.error(error)
            return {"errors": state.errors + [error]}
 
        # --- Pydantic validation -------------------------------------------
        # This is the critical step — ensures LLM output matches our schema
        # exactly before it ever reaches the database or downstream nodes.
        extraction: ExtractionOutput = ExtractionOutput.model_validate_json(raw_json)
 
        logger.info(
            "Extraction complete | action_items: %d | decisions: %d | participants: %d | topics: %d",
            len(extraction.action_items),
            len(extraction.decisions),
            len(extraction.participants),
            len(extraction.key_topics),
        )
 
        return {
            "extraction":      extraction,
            "completed_nodes": state.completed_nodes + ["extract_information"],
        }
 
    except ValidationError as e:
        # LLM returned valid JSON but it didn't match our schema
        # Log the full Pydantic error — it shows exactly which field failed
        error = f"LLM output failed Pydantic validation: {e}"
        logger.error(error)
        return {"errors": state.errors + [error]}
 
    except json.JSONDecodeError as e:
        # Should not happen with response_format=json_object, but handle anyway
        error = f"LLM returned invalid JSON: {e}"
        logger.error(error)
        return {"errors": state.errors + [error]}
 
    except RateLimitError:
        error = "Groq rate limit hit during extraction. Retry after a moment."
        logger.error(error)
        return {"errors": state.errors + [error]}
 
    except APITimeoutError:
        error = "Groq timed out during extraction. Transcript may be too long."
        logger.error(error)
        return {"errors": state.errors + [error]}
 
    except APIConnectionError:
        error = "Could not connect to Groq API during extraction."
        logger.error(error)
        return {"errors": state.errors + [error]}
 
    except APIError as e:
        error = f"Groq API error during extraction: {e.status_code} — {e.message}"
        logger.error(error)
        return {"errors": state.errors + [error]}
 