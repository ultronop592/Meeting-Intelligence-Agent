import asyncio
import logging
import os
import time
from typing import Any

from langgraph.graph import END, StateGraph
from langsmith import traceable

from agents.ambiguity import resolve_ambiguity
from agents.confidence import score_confidence
from agents.extraction import extract_information
from agents.summary import generate_summary
from agents.transcription import transcribe_audio
from agents.verifier import verify_extractions
from core.config import settings
from core.file_cleanup import delete_audio_file
from db.database import save_to_database
from models.schemas import AgentState

logger = logging.getLogger(__name__)


def route_after_transcription(state: AgentState) -> str:
    return "extract_information" if state.transcript and state.transcript.strip() else "end"


def route_after_extraction(state: AgentState) -> str:
    return "verify_extractions" if state.extraction else "end"


def route_after_verification(state: AgentState) -> str:
    if not state.extraction:
        return "end"

    # Feedback loop: if verifier flagged >= 75% of items on first pass,
    # retry extraction with strict prompt feedback up to max 1 retry.
    summary = state.verification_summary or {}
    total = summary.get("total_action_items", 0)
    flagged = summary.get("flagged_action_items", 0)
    retry_count = getattr(state, "verification_retry_count", 0)

    if total > 0 and (flagged / total) >= 0.75 and retry_count < 1:
        logger.warning(
            "Verifier flagged %d/%d items (%d%%). Retrying extraction with feedback (retry=%d).",
            flagged, total, int(flagged / total * 100), retry_count + 1,
        )
        return "retry_extraction"

    return "generate_summary"


def route_after_summary(state: AgentState) -> str:
    return "save_to_database" if state.summary else "end"


def verify_and_score_extractions(state: AgentState) -> dict:
    """Phase 2 Verifier Loop.

    Sequential verification stages:
    1. verify_extractions: Programmatically grounds quotes in transcript & flags hallucinations.
    2. resolve_ambiguity: Prevents guessed owners and vague deadlines; aligns with participants.
    3. score_confidence: Calibrated multi-factor scoring & review policy enforcement (<0.70).
    """
    logger.info("Node 2b — verify_and_score_extractions: starting verification loop")

    # 1. Verification pass
    v_result = verify_extractions(state)
    curr_state = state.model_copy(update={
        "extraction": v_result.get("extraction", state.extraction),
        "verification_summary": v_result.get("verification_summary"),
    })

    # 2. Ambiguity resolution pass
    a_result = resolve_ambiguity(curr_state)
    curr_state = curr_state.model_copy(update={
        "extraction": a_result.get("extraction", curr_state.extraction),
    })

    # 3. Confidence scoring pass
    c_result = score_confidence(curr_state)
    final_extraction = c_result.get("extraction", curr_state.extraction)

    comb_summary = {
        **(v_result.get("verification_summary") or {}),
        **(a_result.get("ambiguity_summary") or {}),
        **(c_result.get("confidence_summary") or {}),
    }

    completed = list(state.completed_nodes or [])
    if "verify_extractions" not in completed:
        completed.append("verify_extractions")

    return {
        "extraction": final_extraction,
        "verification_summary": comb_summary,
        "completed_nodes": completed,
    }


from core.ws_manager import ws_manager

def _make_tracked_node(node_name: str, node_fn):
    if asyncio.iscoroutinefunction(node_fn):
        async def _async_tracked_node(state: AgentState) -> dict | AgentState:
            t0 = time.time()
            if state.job_id:
                try:
                    await ws_manager.broadcast(state.job_id, {
                        "event": "node_started",
                        "node": node_name,
                        "job_id": state.job_id,
                        "completed_nodes": list(state.completed_nodes or []),
                    })
                except Exception:
                    pass
            res = await node_fn(state)
            duration = round((time.time() - t0) * 1000)
            completed = list(state.completed_nodes or [])
            if node_name not in completed:
                completed.append(node_name)
            if state.job_id:
                try:
                    await ws_manager.broadcast(state.job_id, {
                        "event": "node_completed",
                        "node": node_name,
                        "job_id": state.job_id,
                        "completed_nodes": completed,
                        "elapsed_ms": duration,
                    })
                except Exception:
                    pass
            return res
        return _async_tracked_node
    else:
        def _sync_tracked_node(state: AgentState) -> dict | AgentState:
            t0 = time.time()
            if state.job_id:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            ws_manager.broadcast(state.job_id, {
                                "event": "node_started",
                                "node": node_name,
                                "job_id": state.job_id,
                                "completed_nodes": list(state.completed_nodes or []),
                            }),
                            loop,
                        )
                except Exception:
                    pass
            res = node_fn(state)
            duration = round((time.time() - t0) * 1000)
            completed = list(state.completed_nodes or [])
            if node_name not in completed:
                completed.append(node_name)
            if state.job_id:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            ws_manager.broadcast(state.job_id, {
                                "event": "node_completed",
                                "node": node_name,
                                "job_id": state.job_id,
                                "completed_nodes": completed,
                                "elapsed_ms": duration,
                            }),
                            loop,
                        )
                except Exception:
                    pass
            return res
        return _sync_tracked_node


def build_agent_graph():
    graph = StateGraph(AgentState)

    graph.add_node("transcribe_audio", _make_tracked_node("transcribe_audio", transcribe_audio))
    graph.add_node("extract_information", _make_tracked_node("extract_information", extract_information))
    graph.add_node("verify_extractions", _make_tracked_node("verify_extractions", verify_and_score_extractions))
    graph.add_node("generate_summary", _make_tracked_node("generate_summary", generate_summary))
    graph.add_node("save_to_database", _make_tracked_node("save_to_database", save_to_database))

    graph.set_entry_point("transcribe_audio")

    graph.add_conditional_edges(
        "transcribe_audio",
        route_after_transcription,
        {"extract_information": "extract_information", "end": END},
    )
    graph.add_conditional_edges(
        "extract_information",
        route_after_extraction,
        {"verify_extractions": "verify_extractions", "end": END},
    )
    graph.add_conditional_edges(
        "verify_extractions",
        route_after_verification,
        {
            "generate_summary": "generate_summary",
            "retry_extraction": "extract_information",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "generate_summary",
        route_after_summary,
        {"save_to_database": "save_to_database", "end": END},
    )
    graph.add_edge("save_to_database", END)

    return graph.compile()


agent_graph = build_agent_graph()


@traceable(name="arun_meeting_agent", tags=["full-pipeline", "langgraph"], metadata={"nodes": 5})
async def arun_meeting_agent(
    audio_file_path: str,
    audio_filename: str,
    user_id: str | None = None,
    job_id: str | None = None,
    cleanup_audio: bool | None = None,
    storage_key: str | None = None,
) -> AgentState:
    """Asynchronously execute the 5-stage multi-agent meeting pipeline.

    Stages:
      1. transcribe_audio (Whisper Large-v3)
      2. extract_information (Cognitive Intelligence)
      3. verify_extractions (Verifier loop, ambiguity resolution & confidence scoring)
      4. generate_summary (Executive Synthesizer)
      5. save_to_database (Vector Memory & Persistence)

    Integration tools (Jira, Slack, Calendar, Email) are dispatched separately
    via Human-in-the-Loop review after the meeting summary is inspected.
    """
    start_time = time.time()
    initial_state = AgentState(
        audio_file_path=audio_file_path,
        audio_filename=audio_filename,
        user_id=user_id,
        job_id=job_id,
        audio_storage_key=storage_key,
    )
    if not initial_state.audio_storage_key and audio_file_path and os.path.exists(audio_file_path):
        try:
            from core.storage import storage_service
            new_storage_key = f"audio/{user_id or 'shared'}/{int(time.time())}_{audio_filename}"
            uploaded_key = await storage_service.upload_file(audio_file_path, new_storage_key)
            initial_state.audio_storage_key = uploaded_key
        except Exception as storage_exc:
            logger.warning("Could not persist audio to storage service: %s", storage_exc)

    try:
        logger.info("Pipeline execution started for '%s' (User: %s, Job: %s)", audio_filename, user_id or "anonymous", job_id or "none")
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
    finally:
        should_cleanup = cleanup_audio if cleanup_audio is not None else settings.delete_audio_after_processing
        if should_cleanup and audio_file_path:
            delete_audio_file(audio_file_path)


def run_meeting_agent(
    audio_file_path: str,
    audio_filename: str,
    user_id: str | None = None,
    cleanup_audio: bool | None = None,
    storage_key: str | None = None,
) -> AgentState:
    """Synchronous wrapper for arun_meeting_agent for backwards-compatibility / testing."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                asyncio.run,
                arun_meeting_agent(audio_file_path, audio_filename, user_id, cleanup_audio=cleanup_audio, storage_key=storage_key),
            )
            return future.result()
    else:
        return asyncio.run(
            arun_meeting_agent(audio_file_path, audio_filename, user_id, cleanup_audio=cleanup_audio, storage_key=storage_key)
        )

