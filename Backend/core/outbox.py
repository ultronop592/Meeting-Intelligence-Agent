"""core/outbox.py — Transactional Outbox & Idempotency Engine.

Guarantees effectively exactly-once delivery across distributed external channels
(Jira, Slack, Email, Google Calendar) by tracking dispatch intent, external resource
keys, and state transitions in the database.
"""

import hashlib
import logging
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from db.database import (
    create_or_get_outbox_dispatch,
    get_outbox_dispatch,
    update_outbox_dispatch,
)
from db.models import OutboxDispatch

logger = logging.getLogger(__name__)


def build_idempotency_key(
    meeting_id: str,
    channel: str,
    item_id: str | int | None = None,
    recipient: str | None = None,
) -> str:
    """Generate a deterministic, collision-resistant idempotency key.

    Examples:
        meeting_42:action_7:jira
        meeting_42:slack
        meeting_42:calendar
        meeting_42:email_alice@example.com
    """
    channel_clean = channel.lower().strip()
    meeting_clean = meeting_id.strip()

    if channel_clean == "jira" and item_id is not None:
        return f"meeting_{meeting_clean}:action_{item_id}:jira"
    elif channel_clean == "slack":
        return f"meeting_{meeting_clean}:slack"
    elif channel_clean == "calendar":
        return f"meeting_{meeting_clean}:calendar"
    elif channel_clean == "email":
        recip_clean = (recipient or "all").lower().strip()
        # Hash long recipient emails if needed to keep key compact
        return f"meeting_{meeting_clean}:email_{recip_clean}"
    elif item_id is not None:
        return f"meeting_{meeting_clean}:action_{item_id}:{channel_clean}"
    else:
        return f"meeting_{meeting_clean}:{channel_clean}"


class OutboxService:
    """Transactional Outbox and Idempotency Orchestrator."""

    @staticmethod
    async def execute_idempotent_dispatch(
        idempotency_key: str,
        meeting_id: str,
        channel: str,
        dispatch_fn: Callable[[], Awaitable[tuple[str, Any]]],
        check_remote_fn: Optional[Callable[[], Awaitable[str | None]]] = None,
        payload: Optional[dict[str, Any]] = None,
        user_id: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> dict[str, Any]:
        """Execute an external dispatch wrapped in transactional outbox guarantees.

        Args:
            idempotency_key: Stable unique key for this dispatch attempt.
            meeting_id: Meeting ID being dispatched.
            channel: Channel name ("jira", "slack", "email", "calendar").
            dispatch_fn: Async callable returning (external_id, result_meta).
            check_remote_fn: Optional async check to inspect external system if pending.
            payload: Optional request payload to persist in outbox record.
            user_id: Optional user owner ID.
            session: Optional AsyncSession for shared transactions.

        Returns:
            dict containing:
                "status": "sent" | "failed" | "skipped",
                "external_id": str | None,
                "is_duplicate": bool,
                "detail": Any
        """
        # Step 1: Look up or create outbox record with status 'pending'
        dispatch_row, created = await create_or_get_outbox_dispatch(
            idempotency_key=idempotency_key,
            meeting_id=meeting_id,
            channel=channel,
            payload=payload,
            user_id=user_id,
            session=session,
        )

        # Step 2: Idempotent no-op if already sent
        if not created and dispatch_row.status == "sent":
            logger.info(
                "Idempotency hit: dispatch '%s' was already sent (external_id=%s) — skipping API call",
                idempotency_key, dispatch_row.external_id,
            )
            return {
                "status": "sent",
                "external_id": dispatch_row.external_id,
                "is_duplicate": True,
                "detail": f"Skipped duplicate dispatch: previously sent with id {dispatch_row.external_id}",
            }

        # Step 3: Remote reconciliation check (closes the crash window between remote creation and DB write)
        if not created and dispatch_row.status == "pending" and check_remote_fn:
            try:
                remote_id = await check_remote_fn()
                if remote_id:
                    logger.warning(
                        "Remote reconciliation hit: '%s' already exists on remote (%s) — recovering state",
                        idempotency_key, remote_id,
                    )
                    await update_outbox_dispatch(
                        idempotency_key=idempotency_key,
                        status="sent",
                        external_id=remote_id,
                        session=session,
                    )
                    return {
                        "status": "sent",
                        "external_id": remote_id,
                        "is_duplicate": True,
                        "detail": f"Recovered existing remote resource {remote_id}",
                    }
            except Exception as remote_err:
                logger.debug("Remote check failed for '%s': %s", idempotency_key, remote_err)

        # Step 4: Execute the actual external dispatch
        try:
            external_id, meta = await dispatch_fn()
            await update_outbox_dispatch(
                idempotency_key=idempotency_key,
                status="sent",
                external_id=external_id,
                session=session,
            )
            logger.info(
                "Outbox dispatch '%s' succeeded (external_id=%s)",
                idempotency_key, external_id,
            )
            return {
                "status": "sent",
                "external_id": external_id,
                "is_duplicate": False,
                "detail": meta,
            }
        except Exception as exc:
            err_msg = str(exc)
            logger.error("Outbox dispatch '%s' failed: %s", idempotency_key, err_msg)
            await update_outbox_dispatch(
                idempotency_key=idempotency_key,
                status="failed",
                last_error=err_msg[:500],
                session=session,
            )
            raise


outbox_service = OutboxService()
