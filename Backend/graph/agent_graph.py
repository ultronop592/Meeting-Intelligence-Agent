import logging 
from typing import Any 
from langgraph.graph import StateGraph, END
from langsmith import traceable

from Backend.agents.transcription import transcribe_audio
from Backend.agents.extraction import extract_information
from Backend.agents.summary import generate_summary
from Backend.db.database import save_to_database
from Backend.tools.jira_tool import create_jira_tickets
from Backend.tools.calender_tool import book_calendar
from Backend.tools.email_tool import send_notifications
from Backend.models.schemas import AgentState

logger = logging.getLogger(__name__)

# conditional edge function

def rout_after_transcription(state: AgentState) -> str:
    """
    Called after Node 1 (transcribe_audio).
 
    Decision logic:
    - If transcript exists and has content → continue to extraction
    - If transcript is missing or empty    → end the graph immediately
      (no point sending empty text to the LLM — it would hallucinate)
 
    Returns a string key that maps to the next node via path_map dict
    in add_conditional_edges().
    """
    if not state.transcript or not state.transcript.strip():
        logger.warning(
            "Transcript is missing or empty after transcription. "
            "Ending graph execution."
            state.errors,
        )
        return "end"  # maps to END in path_map
    
    logger.info(
        "route_after_transcription: transcript ready (%d words) - continuing."   
        len(state.transcript.split()),
    )
    return "extract_information"  # maps to Node 2 in path_map


def route_after_extraction(state: AgentState) -> str:
    """
    Called after Node 2 (extract_information).
 
    Decision logic:
    - If key information is successfully extracted → continue to summary
    - If extraction fails or returns empty → end the graph immediately
      (no point sending empty data to the LLM — it would hallucinate)
 
    Returns a string key that maps to the next node via path_map dict
    in add_conditional_edges().
    """
    if not state.extracted_info or not state.extracted_info.strip():
        logger.warning(
            "Extraction failed or returned empty after information extraction. "
            "Ending graph execution."
            state.errors,
        )
        return "end"  # maps to END in path_map
    
    logger.info(
        "route_after_extraction: extracted information ready (%d characters) - continuing."   
        len(state.extracted_info),
    )
    return "generate_summary"  # maps to Node 3 in path_map


def route_after_summary(state: AgentState) ->str:
    """
    Called after Node 3 (generate_summary).
 
    Decision logic:
    - If summary is successfully generated → continue to save to database
    - If summary generation fails or returns empty → end the graph immediately
      (no point sending empty data to the LLM — it would hallucinate)
 
    Returns a string key that maps to the next node via path_map dict
    in add_conditional_edges().
    """
    if not state.summary or not state.summary.strip():
        logger.warning(
            "Summary generation failed or returned empty after summary generation. "
            "Ending graph execution."
            state.errors,
        )
        return "end"  # maps to END in path_map
    
    logger.info(
        "route_after_summary: summary ready (%d characters) - continuing."   
        len(state.summary),
    )
    return "save_to_database"  # maps to Node 4 in path_map


def router_after_database(state:AgentState)-> str:
    """Called after Node 4 (save_to_database).
 
    Decision logic:
    - If meeting_id exists → DB save succeeded → continue to integrations
    - If meeting_id is missing → DB save failed → end the graph
      (Nodes 5/6/7 all need meeting_id to log their results.
       Without it we have no way to associate integration results
       with a meeting — better to stop cleanly.)
    """
    if not state.meeting_id:
        logger.error(
            "route_after_database: meeting_id missing — DB save failed. "
            "Ending graph. Errors: %s",
            state.errors,
        )
        return "end"
 
    logger.info(
        "route_after_database: meeting saved — id: %s — continuing to integrations.",
        state.meeting_id,
    )
    return "create_jira_tickets"
 

# Graph Builder 

def build_agent_graph():
    