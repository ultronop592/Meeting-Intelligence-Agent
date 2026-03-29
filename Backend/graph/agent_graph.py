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
    
    