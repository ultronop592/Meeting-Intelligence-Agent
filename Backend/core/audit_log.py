"""core/audit_log.py — Phase 4 Security: Dispatch Audit Logger.

Records every external write attempt (approved or rejected) with full context:
  - WHO requested it (user_id, job_id)
  - WHAT was approved (channel, entity type, entity summary)
  - WHEN it happened (UTC timestamp)
  - WHAT OUTCOME occurred (success / policy_blocked / error)
  - WHY it was blocked (policy rule name, if applicable)

Audit records are written to the ``audit_logs`` Postgres table defined in
``db/models.py``.  They are append-only and should never be deleted (retention
policy permitting).

Usage::

    from core.audit_log import AuditLogger, AuditChannel, AuditOutcome
    from db.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        logger = AuditLogger(session)
        await logger.log(
            user_id="user-123",
            job_id="job-456",
            channel=AuditChannel.JIRA,
            outcome=AuditOutcome.SUCCESS,
            entity_summary="PROJ-42: Finalise Q4 budget",
        )
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums — channel and outcome constants
# ---------------------------------------------------------------------------

class AuditChannel(str, Enum):
    EMAIL    = "email"
    SLACK    = "slack"
    JIRA     = "jira"
    CALENDAR = "calendar"
    MEETING  = "meeting"   # internal pipeline writes (save, delete)
    SYSTEM   = "system"    # policy or system-level events


class AuditOutcome(str, Enum):
    SUCCESS        = "success"
    POLICY_BLOCKED = "policy_blocked"
    ERROR          = "error"
    SKIPPED        = "skipped"


# ---------------------------------------------------------------------------
# Async audit logger
# ---------------------------------------------------------------------------

class AuditLogger:
    """Write structured audit entries to the ``audit_logs`` table.

    Designed to be instantiated per-request or per-job and injected
    wherever external writes are made.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log(
        self,
        *,
        channel: AuditChannel,
        outcome: AuditOutcome,
        entity_summary: str,
        user_id: str | None = None,
        job_id: str | None = None,
        policy_rule: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Append one audit record to the database.

        Args:
            channel:        Which external channel was targeted.
            outcome:        The result of the dispatch attempt.
            entity_summary: Human-readable description (e.g. "PROJ-42: Fix bug").
            user_id:        Owning user ID (None for system-level events).
            job_id:         Processing job ID for traceability.
            policy_rule:    The :class:`~core.policy_gate.PolicyViolation` rule
                            name, if the outcome is ``POLICY_BLOCKED``.
            extra:          Arbitrary additional metadata (stored as JSON).
        """
        try:
            from db.models import AuditLog  # imported here to avoid circular imports
            record = AuditLog(
                user_id=user_id,
                job_id=job_id,
                channel=channel.value,
                outcome=outcome.value,
                entity_summary=entity_summary[:1024],  # truncate long summaries
                policy_rule=policy_rule,
                extra=extra or {},
                created_at=datetime.now(timezone.utc),
            )
            self._session.add(record)
            await self._session.flush()  # write within the current transaction
            logger.info(
                "AUDIT | channel=%s outcome=%s user=%s job=%s rule=%s | %s",
                channel.value, outcome.value, user_id, job_id, policy_rule, entity_summary[:120],
            )
        except Exception as exc:  # audit must never crash the caller
            logger.error("Failed to write audit log: %s", exc, exc_info=True)


# ---------------------------------------------------------------------------
# Convenience: sync helper for non-async contexts (tests, scripts)
# ---------------------------------------------------------------------------

def build_audit_entry(
    channel: AuditChannel,
    outcome: AuditOutcome,
    entity_summary: str,
    user_id: str | None = None,
    job_id: str | None = None,
    policy_rule: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an audit log dict without a DB session (useful in tests)."""
    return {
        "user_id": user_id,
        "job_id": job_id,
        "channel": channel.value,
        "outcome": outcome.value,
        "entity_summary": entity_summary,
        "policy_rule": policy_rule,
        "extra": extra or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
