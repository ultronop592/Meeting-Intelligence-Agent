"""add DB indexes for 10K scale performance

Revision ID: 0003_add_perf_indexes
Revises: 0002_add_audio_storage_key
Create Date: 2026-10-01 21:25:00.000000

Indexes added:
  meetings:
    - ix_meetings_user_created (user_id, created_at DESC) — paginated list queries
  action_items:
    - ix_action_items_meeting_status (meeting_id, status)   — filter by meeting+status
    - ix_action_items_due_date      (due_date)              — reminder cron queries
  participants:
    - ix_participants_meeting_id    (meeting_id)            — join on participants
  decisions:
    - ix_decisions_meeting_id       (meeting_id)            — join on decisions
  processing_jobs:
    - ix_processing_jobs_user_status (user_id, status)      — user's job history
  chat_sessions:
    - ix_chat_sessions_user_updated (user_id, updated_at)  — recent sessions list
"""
from typing import Sequence, Union
from alembic import op


revision: str = "0003_add_perf_indexes"
down_revision: Union[str, None] = "0002_add_audio_storage_key"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # meetings — composite (user_id, created_at) for paginated list queries
    op.create_index(
        "ix_meetings_user_created",
        "meetings",
        ["user_id", "created_at"],
        postgresql_ops={"created_at": "DESC"},
        if_not_exists=True,
    )

    # action_items — (meeting_id, status) for filtering open/done tasks per meeting
    op.create_index(
        "ix_action_items_meeting_status",
        "action_items",
        ["meeting_id", "status"],
        if_not_exists=True,
    )

    # action_items — (due_date) for reminder cron job scans
    op.create_index(
        "ix_action_items_due_date",
        "action_items",
        ["due_date"],
        if_not_exists=True,
    )

    # participants — (meeting_id) for JOIN lookups
    op.create_index(
        "ix_participants_meeting_id",
        "participants",
        ["meeting_id"],
        if_not_exists=True,
    )

    # decisions — (meeting_id) for JOIN lookups
    op.create_index(
        "ix_decisions_meeting_id",
        "decisions",
        ["meeting_id"],
        if_not_exists=True,
    )

    # processing_jobs — (user_id, status) for user's job history queries
    op.create_index(
        "ix_processing_jobs_user_status",
        "processing_jobs",
        ["user_id", "status"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_processing_jobs_user_status", table_name="processing_jobs")
    op.drop_index("ix_decisions_meeting_id",         table_name="decisions")
    op.drop_index("ix_participants_meeting_id",      table_name="participants")
    op.drop_index("ix_action_items_due_date",        table_name="action_items")
    op.drop_index("ix_action_items_meeting_status",  table_name="action_items")
    op.drop_index("ix_meetings_user_created",        table_name="meetings")
