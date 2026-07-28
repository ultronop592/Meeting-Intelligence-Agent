import asyncio
import logging
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


def route_after_database(state: AgentState) -> str:
    return "create_jira_tickets" if state.meeting_id else "end"


def save_to_database_node(state: AgentState) -> dict:
    """Synchronous LangGraph node wrapper for the async save_to_database().

    LangGraph invokes this node from a background thread (via asyncio.to_thread).
    That thread has no running event loop, so we create a fresh one, run the
    coroutine to completion, then close and discard it to avoid any resource leaks.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(save_to_database(state))
    finally:
        loop.close()


def build_agent_graph():
    graph = StateGraph(AgentState)

    graph.add_node("transcribe_audio", transcribe_audio)
    graph.add_node("extract_information", extract_information)
    graph.add_node("generate_summary", generate_summary)
    graph.add_node("save_to_database", save_to_database_node)
    graph.add_node("create_jira_tickets", create_jira_tickets)
    graph.add_node("book_calendar", book_calendar)
    graph.add_node("send_notifications", send_notifications)

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
    graph.add_conditional_edges(
        "save_to_database",
        route_after_database,
        {"create_jira_tickets": "create_jira_tickets", "end": END},
    )

    graph.add_edge("create_jira_tickets", "book_calendar")
    graph.add_edge("book_calendar", "send_notifications")
    graph.add_edge("send_notifications", END)

    return graph.compile()


agent_graph = build_agent_graph()


@traceable(name="run_meeting_agent", tags=["full-pipeline", "langgraph"], metadata={"nodes": 7})
def run_meeting_agent(audio_file_path: str, audio_filename: str) -> AgentState:
    initial_state = AgentState(audio_file_path=audio_file_path, audio_filename=audio_filename)
    try:
        final_state_dict: dict[str, Any] = agent_graph.invoke(initial_state)
        return AgentState(**final_state_dict)
    except Exception as e:
        logger.exception("Graph execution failed: %s", e)
        initial_state.errors.append(f"Unexpected pipeline failure: {e}")
        return initial_state
