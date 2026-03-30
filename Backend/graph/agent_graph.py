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
    """
    Constructs and compiles the LangGraph StateGraph.
 
    Called ONCE at module import time (when FastAPI starts).
    The compiled graph is stored as a module-level singleton below.
 
    GRAPH STRUCTURE:
    ─────────────────────────────────────────────────────────────────
    START
      │
      ▼
    [transcribe_audio] ──(no transcript?)──► END
      │ (transcript exists)
      ▼
    [extract_information] ──(always continues)──►
      │
      ▼
    [generate_summary] ──(no summary?)──► END
      │ (summary exists)
      ▼
    [save_to_database] ──(no meeting_id?)──► END
      │ (meeting_id exists)
      ▼
    [create_jira_tickets]
      │
      ▼
    [book_calendar]
      │
      ▼
    [send_notifications]
      │
      ▼
    END
    ─────────────────────────────────────────────────────────────────
    """
 
    # --- Step 1: Create the graph with our typed state schema ----------------
    # StateGraph(AgentState) tells LangGraph:
    # - Every node receives an AgentState object
    # - Every node returns a dict with a subset of AgentState fields
    # - LangGraph merges those partial updates into the shared state
    graph = StateGraph(AgentState)
 
    # --- Step 2: Register all 7 nodes ----------------------------------------
    # add_node(name, function)
    # - name:     string used in add_edge() and conditional edge path maps
    # - function: any Python callable that takes AgentState and returns dict
    graph.add_node("transcribe_audio",    transcribe_audio)
    graph.add_node("extract_information", extract_information)
    graph.add_node("generate_summary",    generate_summary)
    graph.add_node("save_to_database",    save_to_database)
    graph.add_node("create_jira_tickets", create_jira_tickets)
    graph.add_node("book_calendar",       book_calendar)
    graph.add_node("send_notifications",  send_notifications)
 
    # --- Step 3: Set the entry point -----------------------------------------
    # This tells LangGraph which node to run first when .invoke() is called.
    graph.set_entry_point("transcribe_audio")
 
    # --- Step 4: Add conditional edge after Node 1 ---------------------------
    # add_conditional_edges(source, condition_fn, path_map)
    # - source:       the node that just finished
    # - condition_fn: function that returns a string key
    # - path_map:     maps string key → next node name (or END)
    graph.add_conditional_edges(
        "transcribe_audio",
        route_after_transcription,
        {
            "extract_information": "extract_information",
            "end": END,
        },
    )
 
    # --- Step 5: Add conditional edge after Node 2 ---------------------------
    graph.add_conditional_edges(
        "extract_information",
        route_after_extraction,
        {
            "generate_summary": "generate_summary",
        },
    )
 
    # --- Step 6: Add conditional edge after Node 3 ---------------------------
    graph.add_conditional_edges(
        "generate_summary",
        route_after_summary,
        {
            "save_to_database": "save_to_database",
            "end": END,
        },
    )
 
    # --- Step 7: Add conditional edge after Node 4 ---------------------------
    graph.add_conditional_edges(
        "save_to_database",
        route_after_database,
        {
            "create_jira_tickets": "create_jira_tickets",
            "end": END,
        },
    )
 
    # --- Step 8: Add unconditional edges for Nodes 5 → 6 → 7 ----------------
    # add_edge(A, B) = always go from A to B, no conditions.
    # Nodes 5, 6, 7 always run sequentially after a successful DB save.
    # Even if Jira fails, we continue to Calendar. Even if Calendar fails,
    # we continue to Email/Slack. Failures are logged in state.errors
    # inside each tool function — they do NOT stop the graph here.
    graph.add_edge("create_jira_tickets", "book_calendar")
    graph.add_edge("book_calendar",       "send_notifications")
    graph.add_edge("send_notifications",  END)
 
    # --- Step 9: Compile the graph -------------------------------------------
    # compile() does two things:
    # 1. Validates the graph — checks for orphaned nodes, missing edges,
    #    unreachable nodes, etc. Catches mistakes at startup not at runtime.
    # 2. Returns a Runnable with .invoke(), .stream(), and .ainvoke() methods.
    compiled = graph.compile()
 
    logger.info(
        "LangGraph StateGraph compiled successfully — "
        "7 nodes | 4 conditional edges | 3 unconditional edges"
    )
 
    return compiled
 
 
# =============================================================================
# MODULE-LEVEL SINGLETON
# =============================================================================
# The compiled graph is created ONCE when this module is imported.
# FastAPI imports this module at startup — so the graph is ready before
# the first request arrives.
#
# Thread safety: LangGraph compiled graphs are stateless. All state is
# passed IN via .invoke(initial_state) and returned OUT as the result.
# Nothing is stored in the graph object itself. Multiple FastAPI workers
# can use the same compiled graph simultaneously without any issues.
# =============================================================================
 
agent_graph = build_agent_graph()
 
 
# =============================================================================
# PUBLIC RUNNER FUNCTION
# =============================================================================
# This is what FastAPI routes.py calls.
# It wraps the graph invocation with logging, error handling,
# and LangSmith tracing.
# =============================================================================
 
@traceable(
    name="run_meeting_agent",
    tags=["full-pipeline", "langgraph"],
    metadata={"nodes": 7, "version": "2.0.0"},
)
def run_meeting_agent(
    audio_file_path: str,
    audio_filename:  str,
) -> AgentState:
    """
    Entry point called by FastAPI background task in routes.py.
 
    Creates the initial AgentState, runs the compiled LangGraph pipeline,
    and returns the final state with all results populated.
 
    ARGS:
        audio_file_path — absolute server-side path to the audio file
        audio_filename  — original filename for display (e.g. "standup.mp3")
 
    RETURNS:
        AgentState — final state after all nodes have run.
        Always returns — never raises. Errors are in state.errors.
 
    CALLED FROM:
        backend/api/routes.py — inside a FastAPI BackgroundTask or
        asyncio.run_in_executor() so it doesn't block the event loop.
 
    EXAMPLE:
        state = run_meeting_agent(
            audio_file_path="/tmp/uploads/meeting.mp3",
            audio_filename="standup-2026-03-25.mp3",
        )
        print(state.meeting_id)      # UUID saved to DB
        print(state.completed_nodes) # ["transcribe_audio", "extract_information", ...]
        print(state.errors)          # [] if all good, or list of error strings
    """
    logger.info(
        "run_meeting_agent: starting pipeline | file: %s",
        audio_filename,
    )
 
    # Build the initial state — only input fields are set.
    # All output fields default to None / empty list.
    # Each node will populate its own fields as it runs.
    initial_state = AgentState(
        audio_file_path=audio_file_path,
        audio_filename=audio_filename,
    )
 
    try:
        # invoke() runs the full graph synchronously.
        # It returns a plain dict of the final merged state.
        # LangGraph guarantees this dict contains every field from AgentState.
        final_state_dict: dict[str, Any] = agent_graph.invoke(initial_state)
 
        # Convert the dict back to a typed AgentState object
        # so the caller gets full type safety and IDE autocomplete.
        final_state = AgentState(**final_state_dict)
 
        # Log the outcome
        if final_state.errors:
            logger.warning(
                "run_meeting_agent: pipeline completed with %d non-fatal error(s): %s",
                len(final_state.errors),
                final_state.errors,
            )
        else:
            logger.info(
                "run_meeting_agent: pipeline completed successfully | "
                "meeting_id: %s | nodes: %s",
                final_state.meeting_id,
                final_state.completed_nodes,
            )
 
        return final_state
 
    except Exception as e:
        # This catch is for unexpected LangGraph-level failures —
        # not node-level failures (those are handled inside each node).
        # In practice this should almost never trigger.
        logger.exception(
            "run_meeting_agent: unexpected graph-level failure: %s", e
        )
 
        # Return the initial state with the error recorded
        # so the caller always gets an AgentState back, never an exception.
        initial_state.errors.append(f"Unexpected pipeline failure: {str(e)}")
        return initial_state
 