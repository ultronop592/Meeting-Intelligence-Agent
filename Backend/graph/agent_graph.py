import asyncio
import logging
import time
from typing import Any

from langgraph.graph import END, StateGraph
from langsmith import traceable

from agents.extraction import extract_information
from agents.summary import generate_summary
from agents.transcription import transcribe_audio
from db.database import save_to_database
from models.schemas import AgentState
from tools.calender_tool import book_calendar
from tools.jira_tool import create_jira_tickets
from tools.slack_tool import send_notifications

logger = logging.getLogger(__name__)


def route_after_transcription(state: AgentState) -> str:
    return "extract_information" if state.transcript and state.transcript.strip() else "end"


def route_after_extraction(state: AgentState) -> str:
    return "generate_summary" if state.extraction else "end"


def route_after_summary(state: AgentState) -> str:
    return "save_to_database" if state.summary else "end"


def build_agent_graph():
    graph = StateGraph(AgentState)

    graph.add_node("transcribe_audio", transcribe_audio)
    graph.add_node("extract_information", extract_information)
    graph.add_node("generate_summary", generate_summary)
    graph.add_node("save_to_database", save_to_database)

    graph.set_entry_point("transcribe_audio")

    graph.add_conditional_edges(
        "transcribe_audio",
        route_after_transcription,
        {"extract_information": "extract_information", "end": END},
    )
    graph.add_conditional_edges(
        "extract_information",
        route_after_extraction,
        {"generate_summary": "generate_summary", "end": END},
    )
    graph.add_conditional_edges(
        "generate_summary",
        route_after_summary,
        {"save_to_database": "save_to_database", "end": END},
    )
    graph.add_edge("save_to_database", END)

    return graph.compile()


agent_graph = build_agent_graph()


@traceable(name="arun_meeting_agent", tags=["full-pipeline", "langgraph"], metadata={"nodes": 4})
async def arun_meeting_agent(audio_file_path: str, audio_filename: str, user_id: str | None = None) -> AgentState:
    """Asynchronously execute the 4-stage multi-agent meeting pipeline.

    Stages:
      1. transcribe_audio (Whisper Large-v3)
      2. extract_information (Cognitive Intelligence)
      3. generate_summary (Executive Synthesizer)
      4. save_to_database (Vector Memory & Persistence)

    Integration tools (Jira, Slack, Calendar, Email) are dispatched separately
    via Human-in-the-Loop review after the meeting summary is inspected.
    """
    start_time = time.time()
    initial_state = AgentState(
        audio_file_path=audio_file_path,
        audio_filename=audio_filename,
        user_id=user_id,
    )
    try:
        logger.info("Pipeline execution started for '%s' (User: %s)", audio_filename, user_id or "anonymous")
        final_state_dict: dict[str, Any] = await agent_graph.ainvoke(initial_state)
        result = AgentState(**final_state_dict)

        total_duration_ms = round((time.time() - start_time) * 1000)
        node_timings = getattr(result, "node_timings", {})
        logger.info(
            "Pipeline finished in %d ms. Node timing breakdown: %s | Errors count: %d",
            total_duration_ms,
            node_timings,
            len(result.errors),
        )
        return result
    except Exception as e:
        total_duration_ms = round((time.time() - start_time) * 1000)
        logger.exception("Graph execution failed after %d ms: %s", total_duration_ms, e)
        initial_state.errors.append(f"Unexpected pipeline failure: {e}")
        return initial_state


def run_meeting_agent(audio_file_path: str, audio_filename: str, user_id: str | None = None) -> AgentState:
    """Synchronous wrapper for arun_meeting_agent for backwards-compatibility / testing."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, arun_meeting_agent(audio_file_path, audio_filename, user_id))
            return future.result()
    else:
        return asyncio.run(arun_meeting_agent(audio_file_path, audio_filename, user_id))

