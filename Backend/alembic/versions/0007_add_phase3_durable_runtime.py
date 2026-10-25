"""add phase 3 durable runtime: outbox dispatches table and processing job checkpoint fields

Revision ID: 0007_add_phase3_durable_runtime
Revises: 0006_add_verification_and_evidence_fields
Create Date: 2026-10-25 14:00:00.000000

Adds:
- outbox_dispatches table for idempotent external delivery (Jira, Slack, Email, Calendar)
- checkpoint_state, last_heartbeat, worker_id, and retry_count columns to processing_jobs
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "0007_add_phase3_durable_runtime"
down_revision: Union[str, None] = "0006_add_verification_and_evidence_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create outbox_dispatches table
    op.create_table(
        "outbox_dispatches",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("meeting_id", sa.String(), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_outbox_dispatches_key", "outbox_dispatches", ["idempotency_key"], unique=True)
    op.create_index("ix_outbox_dispatches_meeting_status", "outbox_dispatches", ["meeting_id", "status"], unique=False)
    op.create_index("ix_outbox_dispatches_channel", "outbox_dispatches", ["channel"], unique=False)

    # 2. Add checkpointing and worker recovery columns to processing_jobs
    op.add_column("processing_jobs", sa.Column("checkpoint_state", sa.JSON(), nullable=True))
    op.add_column("processing_jobs", sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True))
    op.add_column("processing_jobs", sa.Column("worker_id", sa.String(length=128), nullable=True))
    op.add_column("processing_jobs", sa.Column("retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False))
    op.create_index("ix_processing_jobs_heartbeat", "processing_jobs", ["last_heartbeat"], unique=False)


def downgrade() -> None:
    # 1. Rollback processing_jobs additions
    op.drop_index("ix_processing_jobs_heartbeat", table_name="processing_jobs")
    op.drop_column("processing_jobs", "retry_count")
    op.drop_column("processing_jobs", "worker_id")
    op.drop_column("processing_jobs", "last_heartbeat")
    op.drop_column("processing_jobs", "checkpoint_state")

    # 2. Rollback outbox_dispatches table
    op.drop_index("ix_outbox_dispatches_channel", table_name="outbox_dispatches")
    op.drop_index("ix_outbox_dispatches_meeting_status", table_name="outbox_dispatches")
    op.drop_index("ix_outbox_dispatches_key", table_name="outbox_dispatches")
    op.drop_table("outbox_dispatches")
