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
from db.database import get_job_checkpoint, save_job_checkpoint, save_to_database, update_job_heartbeat
from models.schemas import AgentState, ExtractionOutput, MeetingSummary

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

def _serialize_node_output(node_name: str, result: Any) -> dict[str, Any]:
    """Convert node output into JSON-serializable dictionary for checkpoint storage."""
    if not isinstance(result, dict):
        return {}
    out: dict[str, Any] = {}
    for k, v in result.items():
        if k in ("node_timings",):
            continue
        if hasattr(v, "model_dump"):
            out[k] = v.model_dump(mode="json")
        elif hasattr(v, "dict"):
            out[k] = v.dict()
        elif isinstance(v, (str, int, float, bool, list, dict)) or v is None:
            out[k] = v
    return out


def _hydrate_state_from_checkpoint(state: AgentState, checkpoint_info: dict) -> AgentState:
    """Populate AgentState with completed node outputs from database checkpoint."""
    cp = checkpoint_info.get("checkpoint_state") or {}
    completed = list(checkpoint_info.get("completed_nodes") or [])
    update_data: dict[str, Any] = {
        "checkpoint_state": cp,
        "completed_nodes": completed,
        "resumed_from_checkpoint": True,
    }

    # Node 1: transcribe_audio
    trans_cp = cp.get("transcribe_audio") or {}
    if trans_cp:
        for fld in ("transcript", "speaker_segments", "transcript_words", "diarized_transcript"):
            if fld in trans_cp and trans_cp[fld] is not None:
                update_data[fld] = trans_cp[fld]

    # Node 2 / 2b: extraction
    ext_cp = (cp.get("verify_extractions") or {}).get("extraction") or (cp.get("extract_information") or {}).get("extraction")
    if ext_cp:
        try:
            update_data["extraction"] = ExtractionOutput.model_validate(ext_cp) if isinstance(ext_cp, dict) else ext_cp
        except Exception as exc:
            logger.debug("Failed validating extraction from checkpoint: %s", exc)

    ver_summary = (cp.get("verify_extractions") or {}).get("verification_summary")
    if ver_summary:
        update_data["verification_summary"] = ver_summary

    # Node 3: generate_summary
    sum_cp = (cp.get("generate_summary") or {}).get("summary")
    if sum_cp:
        try:
            update_data["summary"] = MeetingSummary.model_validate(sum_cp) if isinstance(sum_cp, dict) else sum_cp
        except Exception as exc:
            logger.debug("Failed validating summary from checkpoint: %s", exc)

    # Node 4: save_to_database
    db_cp = cp.get("save_to_database") or {}
    if "meeting_id" in db_cp:
        update_data["meeting_id"] = db_cp["meeting_id"]

    return state.model_copy(update=update_data)


def _make_tracked_node(node_name: str, node_fn):
    if asyncio.iscoroutinefunction(node_fn):
        async def _async_tracked_node(state: AgentState) -> dict | AgentState:
            # Checkpoint resume path: if already finished, skip costly re-execution!
            if state.resumed_from_checkpoint and node_name in (state.completed_nodes or []):
                cp_data = (state.checkpoint_state or {}).get(node_name)
                if cp_data:
                    logger.info("Resumed from checkpoint: skipping finished node '%s'", node_name)
                    if state.job_id:
                        try:
                            await update_job_heartbeat(state.job_id)
                            await ws_manager.broadcast(state.job_id, {
                                "event": "node_restored_from_checkpoint",
                                "node": node_name,
                                "job_id": state.job_id,
                                "completed_nodes": list(state.completed_nodes or []),
                            })
                        except Exception:
                            pass
                    return cp_data

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
                    serialized = _serialize_node_output(node_name, res)
                    await save_job_checkpoint(
                        job_id=state.job_id,
                        node_name=node_name,
                        node_data={node_name: serialized},
                        completed_nodes=completed,
                    )
                except Exception as cp_err:
                    logger.debug("Failed to save checkpoint for %s: %s", node_name, cp_err)

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
            # Checkpoint resume path: if already finished, skip costly re-execution!
            if state.resumed_from_checkpoint and node_name in (state.completed_nodes or []):
                cp_data = (state.checkpoint_state or {}).get(node_name)
                if cp_data:
                    logger.info("Resumed from checkpoint: skipping finished node '%s'", node_name)
                    return cp_data

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
                        serialized = _serialize_node_output(node_name, res)
                        asyncio.run_coroutine_threadsafe(
                            save_job_checkpoint(
                                job_id=state.job_id,
                                node_name=node_name,
                                node_data={node_name: serialized},
                                completed_nodes=completed,
                            ),
                            loop,
                        )
                except Exception:
                    pass

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

    # Checkpoint recovery: check if a previous run produced intermediate state for this job
    if job_id:
        try:
            checkpoint_info = await get_job_checkpoint(job_id)
            if checkpoint_info and checkpoint_info.get("checkpoint_state"):
                logger.info(
                    "Job %s has existing checkpoint (completed: %s) — hydrating pipeline state",
                    job_id, checkpoint_info.get("completed_nodes"),
                )
                initial_state = _hydrate_state_from_checkpoint(initial_state, checkpoint_info)
        except Exception as cp_load_err:
            logger.warning("Could not load checkpoint for job %s: %s", job_id, cp_load_err)
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

