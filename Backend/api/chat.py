"""Domain router: Meeting Intelligence Conversational Agent & Chat Sessions.

Endpoints:
- GET    /chat/sessions: List user's multi-turn conversational chat sessions.
- POST   /chat/sessions: Create a new conversational chat session.
- GET    /chat/sessions/{session_id}: Retrieve full message history of a chat session.
- DELETE /chat/sessions/{session_id}: Delete a chat session.
- POST   /query: Conversational Q&A endpoint powered by OpenRouter with meeting context.
- POST   /query/stream: Streaming LLM Q&A endpoint using Server-Sent Events (SSE).
- POST   /memory/search: Search cross-meeting vector memory using semantic similarity.
"""

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from core.config import settings
from core.openrouter_client import openrouter_client
from db.database import (
    append_chat_session_turn,
    create_chat_session,
    delete_chat_session,
    get_chat_session,
    get_db,
    list_chat_sessions,
)
from db.models import ActionItem as DBActionItem, Decision, Meeting, Participant, User
from models.schemas import (
    AgentQueryRequest,
    AgentQueryResponse,
    ChatSessionDetail,
    ChatSessionListItem,
    CreateChatSessionRequest,
    MemorySearchRequest,
    MemorySearchResponse,
)

logger = logging.getLogger(__name__)

chat_router = APIRouter(tags=["agent"])

SYSTEM_CHAT_PROMPT = (
    "You are an elite Meeting Intelligence AI Agent powered by advanced LLM reasoning. "
    "You have comprehensive access to all details of the user's meeting discussions, including "
    "executive summaries, detailed minutes, assigned action items with owners and deadlines, "
    "architectural and business decisions, attendees with speaker labels, and the complete verbatim dialogue transcript.\n\n"
    "INSTRUCTIONS:\n"
    "1. Answer questions thoroughly, accurately, and naturally based strictly on the provided meeting context.\n"
    "2. When asked about action items, explicitly detail who owns them, the urgency/priority, status, and due dates.\n"
    "3. When asked about decisions, opinions, or debates, cite specific quotes or speaker turns from the transcript.\n"
    "4. Format your responses with clean, readable GitHub-flavored Markdown (bolding, structured bullet points, numbered lists, or tables).\n"
    "5. If a question cannot be answered from the meeting record, state that clearly and mention what related topics were covered.\n"
    "6. Maintain a helpful, confident, executive pair-programmer and chief-of-staff tone."
)


async def _build_full_meeting_context(
    db: AsyncSession,
    question: str,
    meeting_id: str | None = None,
    current_user: User | None = None,
) -> tuple[str, list[str]]:
    """Build comprehensive context from the meeting record, full transcript, actions, decisions, and memory."""
    user_filter = (Meeting.user_id == current_user.id) | (Meeting.user_id.is_(None)) if current_user else True
    target_meeting: Meeting | None = None
    mem_matches: list[dict] = []
    sources: list[str] = []

    from core.memory_service import memory_service

    if meeting_id:
        target_meeting = await db.get(Meeting, meeting_id)
        if target_meeting and current_user and target_meeting.user_id and target_meeting.user_id != current_user.id:
            target_meeting = None
        if target_meeting:
            sources.append(f"meeting:{target_meeting.id}:{target_meeting.title}")
            try:
                mem_matches = await memory_service.search_memory(
                    db,
                    question,
                    top_k=2,
                    exclude_meeting_id=target_meeting.id,
                    user_id=current_user.id if current_user else None,
                )
                for mm in mem_matches:
                    sources.append(f"memory:{mm['meeting_id']}:{mm['title']}")
            except Exception as mem_exc:
                logger.debug("Memory search error: %s", mem_exc)
    else:
        try:
            mem_matches = await memory_service.search_memory(
                db,
                question,
                top_k=4,
                user_id=current_user.id if current_user else None,
            )
        except Exception as mem_exc:
            logger.debug("Global memory search error: %s", mem_exc)
            mem_matches = []

        if mem_matches:
            top_id = mem_matches[0]["meeting_id"]
            target_meeting = await db.get(Meeting, top_id)
            for mm in mem_matches:
                sources.append(f"meeting:{mm['meeting_id']}:{mm['title']}")
            mem_matches = mem_matches[1:]
        else:
            stmt = select(Meeting).where(user_filter).order_by(Meeting.created_at.desc()).limit(1)
            target_meeting = (await db.execute(stmt)).scalars().first()
            if target_meeting:
                sources.append(f"meeting:{target_meeting.id}:{target_meeting.title}")

    if not target_meeting:
        return "", []

    action_items = (
        await db.execute(
            select(DBActionItem).where(DBActionItem.meeting_id == target_meeting.id).order_by(DBActionItem.created_at)
        )
    ).scalars().all()

    decisions = (
        await db.execute(
            select(Decision).where(Decision.meeting_id == target_meeting.id).order_by(Decision.created_at)
        )
    ).scalars().all()

    participants = (
        await db.execute(
            select(Participant).where(Participant.meeting_id == target_meeting.id).order_by(Participant.created_at)
        )
    ).scalars().all()

    context_sections: list[str] = [
        f"PRIMARY RELEVANT MEETING: {target_meeting.title}",
        f"RECORDED AT: {target_meeting.created_at.isoformat() if target_meeting.created_at else 'Unknown'}",
        f"DURATION: {target_meeting.duration_minutes} minutes" if target_meeting.duration_minutes else "DURATION: Not recorded",
    ]

    if target_meeting.short_summary:
        context_sections.append(f"EXECUTIVE SUMMARY:\n{target_meeting.short_summary}")

    if target_meeting.detailed_summary:
        context_sections.append(f"DETAILED MINUTES & TOPICS:\n{target_meeting.detailed_summary}")

    if participants:
        part_lines = []
        for p in participants:
            label = f" ({p.speaker_label})" if p.speaker_label else ""
            email = f" <{p.email}>" if p.email else ""
            part_lines.append(f"- {p.name}{label}{email}")
        context_sections.append("PARTICIPANTS & SPEAKERS:\n" + "\n".join(part_lines))

    if action_items:
        items_lines = [
            f"- [Status: {item.status.value if hasattr(item.status, 'value') else item.status}] {item.description} | Owner: {item.owner or 'Unassigned'} | Priority: {item.priority.value if hasattr(item.priority, 'value') else item.priority} | Due: {item.due_date or 'No deadline'}"
            for item in action_items
        ]
        context_sections.append("ACTION ITEMS & ASSIGNMENTS:\n" + "\n".join(items_lines))

    if decisions:
        dec_lines = [
            f"- {d.description} (Context: {d.context})" if d.context else f"- {d.description}"
            for d in decisions
        ]
        context_sections.append("KEY DECISIONS MADE:\n" + "\n".join(dec_lines))

    transcript_text = getattr(target_meeting, "diarized_transcript", None) or getattr(target_meeting, "transcript", None)
    if transcript_text:
        context_sections.append(f"VERBATIM MEETING DIALOGUE TRANSCRIPT:\n{transcript_text[:60000]}")

    if mem_matches:
        mem_block = ["=== RELEVANT CROSS-MEETING MEMORY & HISTORICAL INTELLIGENCE ==="]
        for m_match in mem_matches:
            mem_block.append(f"\n[Past Meeting]: \"{m_match['title']}\" (Date: {m_match['date']}, Similarity: {round(m_match.get('similarity_score', 0) * 100)}%)")
            if m_match.get("short_summary"):
                mem_block.append(f"Summary: {m_match['short_summary']}")
            if m_match.get("decisions"):
                decs_str = "; ".join(f"{d['description']}" for d in m_match["decisions"][:3])
                mem_block.append(f"Decisions: {decs_str}")
            if m_match.get("action_items"):
                actions_str = "; ".join(f"{a['description']} (owner: {a['owner']}, status: {a['status']})" for a in m_match["action_items"][:3])
                mem_block.append(f"Action Items: {actions_str}")
        context_sections.append("\n".join(mem_block))

    full_context = "\n\n".join(context_sections)
    return full_context, sources


def _get_fallback_rule_answer(meeting_context: str, question: str) -> str:
    lower_question = question.lower()
    if any(term in lower_question for term in ("how many people", "participants", "who attended", "attendees")):
        return "Please refer to the participants section extracted for this meeting."
    elif any(term in lower_question for term in ("action", "task", "todo", "assigned")):
        return "Action items and owners are listed in the meeting details."
    elif "decision" in lower_question:
        return "Decisions made during this meeting are summarized in the decision log."
    return "The meeting record and summary have been loaded. Please ask a specific question regarding topics discussed."


@chat_router.get("/chat/sessions", response_model=list[ChatSessionListItem])
async def get_chat_sessions(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List conversational chat sessions for the current user."""
    return await list_chat_sessions(user_id=current_user.id, limit=limit, offset=offset, db=db)


@chat_router.post("/chat/sessions", response_model=ChatSessionDetail)
async def create_new_chat_session(
    payload: CreateChatSessionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Explicitly create a new chat session."""
    return await create_chat_session(
        user_id=current_user.id,
        meeting_id=payload.meeting_id,
        title=payload.title,
        db=db,
    )


@chat_router.get("/chat/sessions/{session_id}", response_model=ChatSessionDetail)
async def get_single_chat_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve a specific chat session with its full message history."""
    sess = await get_chat_session(session_id=session_id, db=db)
    if not sess:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    if sess.get("user_id") and sess["user_id"] != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access to chat session denied")
    return sess


@chat_router.delete("/chat/sessions/{session_id}")
async def remove_chat_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a chat session."""
    sess = await get_chat_session(session_id=session_id, db=db)
    if not sess:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    if sess.get("user_id") and sess["user_id"] != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access to chat session denied")
    deleted = await delete_chat_session(session_id=session_id, user_id=current_user.id, db=db)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Failed to delete chat session")
    return {"ok": True, "message": "Chat session deleted"}


@chat_router.post("/query", response_model=AgentQueryResponse)
async def query_agent(
    payload: AgentQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Conversational Q&A endpoint powered by OpenRouter with full meeting context."""
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Question cannot be empty")

    session_id = payload.session_id or str(uuid.uuid4())
    prior_messages: list[dict] = []
    if payload.session_id:
        existing_session = await get_chat_session(payload.session_id, db=db)
        if existing_session:
            if existing_session.get("user_id") and existing_session["user_id"] != current_user.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access to chat session denied")
            prior_messages = existing_session.get("messages") or []

    meeting_context, sources = await _build_full_meeting_context(
        db=db,
        question=question,
        meeting_id=payload.meeting_id,
        current_user=current_user,
    )

    if not meeting_context:
        no_meetings_msg = "No meetings are available yet in this workspace. Upload and process a recording first."
        await append_chat_session_turn(
            session_id=session_id,
            user_message=question,
            assistant_message=no_meetings_msg,
            sources=[],
            user_id=current_user.id,
            meeting_id=payload.meeting_id,
            db=db,
        )
        return AgentQueryResponse(
            answer=no_meetings_msg,
            sources=[],
            session_id=session_id,
        )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": f"{SYSTEM_CHAT_PROMPT}\n\n=== FULL MEETING CONTEXT ===\n{meeting_context}"}
    ]
    if prior_messages:
        for m in prior_messages[-10:]:
            if isinstance(m, dict) and m.get("role") in ("user", "assistant"):
                messages.append({"role": m["role"], "content": m.get("content", "")})
    elif payload.history:
        for h in payload.history[-10:]:
            if h.role in ("user", "assistant"):
                messages.append({"role": h.role, "content": h.content})

    messages.append({"role": "user", "content": question})

    answer = None

    # 1. Primary: OpenRouter LLM
    if openrouter_client.is_configured:
        try:
            answer = await openrouter_client.chat_completion(messages)
        except Exception as exc:
            logger.warning("OpenRouter chat completion failed: %s", exc)

    # 2. Secondary fallback: Groq
    if not answer and settings.groq_api_key:
        try:
            from groq import Groq
            client = Groq(api_key=settings.groq_api_key, timeout=20)
            completion = await asyncio.to_thread(
                client.chat.completions.create,
                model=settings.llm_fast_model,
                messages=messages,
                temperature=0.2,
                max_tokens=800,
            )
            answer = completion.choices[0].message.content.strip()
        except Exception as exc:
            logger.warning("Groq fallback query failed: %s", exc)

    # 3. Tertiary fallback: Rule-based matcher
    if not answer:
        answer = _get_fallback_rule_answer(meeting_context, question)

    await append_chat_session_turn(
        session_id=session_id,
        user_message=question,
        assistant_message=answer,
        sources=sources,
        user_id=current_user.id,
        meeting_id=payload.meeting_id,
        db=db,
    )

    return AgentQueryResponse(answer=answer, sources=sources, session_id=session_id)


@chat_router.post("/query/stream")
async def query_agent_stream(
    payload: AgentQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Streaming LLM Q&A endpoint using Server-Sent Events (SSE) powered by OpenRouter."""
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Question cannot be empty")

    session_id = payload.session_id or str(uuid.uuid4())
    prior_messages: list[dict] = []
    if payload.session_id:
        existing_session = await get_chat_session(payload.session_id, db=db)
        if existing_session:
            if existing_session.get("user_id") and existing_session["user_id"] != current_user.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access to chat session denied")
            prior_messages = existing_session.get("messages") or []

    meeting_context, sources = await _build_full_meeting_context(
        db=db,
        question=question,
        meeting_id=payload.meeting_id,
        current_user=current_user,
    )

    if not meeting_context:
        async def empty_stream():
            msg = "No meetings are available yet in this workspace. Upload and process a recording first."
            yield f"data: {json.dumps({'chunk': msg})}\n\n"
            await append_chat_session_turn(
                session_id=session_id,
                user_message=question,
                assistant_message=msg,
                sources=[],
                user_id=current_user.id,
                meeting_id=payload.meeting_id,
                db=db,
            )
            yield f"data: {json.dumps({'done': True, 'sources': [], 'session_id': session_id})}\n\n"
        return StreamingResponse(empty_stream(), media_type="text/event-stream")

    messages: list[dict[str, str]] = [
        {"role": "system", "content": f"{SYSTEM_CHAT_PROMPT}\n\n=== FULL MEETING CONTEXT ===\n{meeting_context}"}
    ]
    if prior_messages:
        for m in prior_messages[-10:]:
            if isinstance(m, dict) and m.get("role") in ("user", "assistant"):
                messages.append({"role": m["role"], "content": m.get("content", "")})
    elif payload.history:
        for h in payload.history[-10:]:
            if h.role in ("user", "assistant"):
                messages.append({"role": h.role, "content": h.content})

    messages.append({"role": "user", "content": question})

    async def sse_generator():
        stream_succeeded = False
        collected_chunks: list[str] = []

        # 1. Primary: OpenRouter Streaming
        if openrouter_client.is_configured:
            try:
                has_tokens = False
                async for token in openrouter_client.stream_chat_completion(messages):
                    has_tokens = True
                    collected_chunks.append(token)
                    yield f"data: {json.dumps({'chunk': token})}\n\n"

                if has_tokens:
                    stream_succeeded = True
                    full_answer = "".join(collected_chunks)
                    await append_chat_session_turn(
                        session_id=session_id,
                        user_message=question,
                        assistant_message=full_answer,
                        sources=sources,
                        user_id=current_user.id,
                        meeting_id=payload.meeting_id,
                        db=db,
                    )
                    yield f"data: {json.dumps({'done': True, 'sources': sources, 'model': openrouter_client.default_model, 'session_id': session_id})}\n\n"
                    return
            except Exception as exc:
                logger.warning("OpenRouter stream failed, attempting fallback: %s", exc)

        # 2. Secondary fallback: Groq Streaming
        if not stream_succeeded and settings.groq_api_key:
            try:
                from groq import Groq
                client = Groq(api_key=settings.groq_api_key, timeout=20)
                def create_groq_stream():
                    return client.chat.completions.create(
                        model=settings.llm_fast_model,
                        messages=messages,
                        temperature=0.2,
                        max_tokens=800,
                        stream=True,
                    )
                stream = await asyncio.to_thread(create_groq_stream)
                for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    if delta:
                        stream_succeeded = True
                        collected_chunks.append(delta)
                        yield f"data: {json.dumps({'chunk': delta})}\n\n"

                if stream_succeeded:
                    full_answer = "".join(collected_chunks)
                    await append_chat_session_turn(
                        session_id=session_id,
                        user_message=question,
                        assistant_message=full_answer,
                        sources=sources,
                        user_id=current_user.id,
                        meeting_id=payload.meeting_id,
                        db=db,
                    )
                    yield f"data: {json.dumps({'done': True, 'sources': sources, 'model': settings.llm_fast_model, 'session_id': session_id})}\n\n"
                    return
            except Exception as exc:
                logger.warning("Groq stream fallback failed: %s", exc)

        # 3. Tertiary fallback: rule-based word-by-word emission
        fallback_text = _get_fallback_rule_answer(meeting_context, question)
        words = fallback_text.split(" ")
        for i, word in enumerate(words):
            space = " " if i > 0 else ""
            collected_chunks.append(space + word)
            yield f"data: {json.dumps({'chunk': space + word})}\n\n"
            await asyncio.sleep(0.015)

        full_answer = "".join(collected_chunks)
        await append_chat_session_turn(
            session_id=session_id,
            user_message=question,
            assistant_message=full_answer,
            sources=sources,
            user_id=current_user.id,
            meeting_id=payload.meeting_id,
            db=db,
        )
        yield f"data: {json.dumps({'done': True, 'sources': sources, 'fallback': True, 'session_id': session_id})}\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")


@chat_router.post("/memory/search", response_model=MemorySearchResponse)
async def search_memory(
    payload: MemorySearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search cross-meeting vector memory using semantic similarity."""
    from core.memory_service import memory_service
    matches = await memory_service.search_memory(db, payload.query, top_k=payload.top_k, user_id=current_user.id)
    return MemorySearchResponse(
        query=payload.query,
        results_count=len(matches),
        matches=matches,
    )
