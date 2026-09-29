"""Initial schema baseline

Revision ID: 0001_initial_schema
Revises: None
Create Date: 2026-09-29 20:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy


# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure pgvector extension is available in Postgres
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Table 0: users
    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    # Table 1: meetings
    op.create_table(
        "meetings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("audio_filename", sa.String(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("short_summary", sa.Text(), nullable=False),
        sa.Column("detailed_summary", sa.Text(), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("diarized_transcript", sa.Text(), nullable=True),
        sa.Column(
            "embedding_status",
            sa.Enum("pending", "completed", "failed", name="embeddingstatus"),
            nullable=False,
        ),
        sa.Column(
            "transcript_embedding",
            pgvector.sqlalchemy.Vector(768),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Table 2: user_tool_credentials
    op.create_table(
        "user_tool_credentials",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("tool_name", sa.String(), nullable=False),
        sa.Column("credentials", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "tool_name", name="uq_user_tool"),
    )
    op.create_index(
        op.f("ix_user_tool_credentials_tool_name"),
        "user_tool_credentials",
        ["tool_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_tool_credentials_user_id"),
        "user_tool_credentials",
        ["user_id"],
        unique=False,
    )

    # Table 3: action_items
    op.create_table(
        "action_items",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("meeting_id", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("owner", sa.String(), nullable=False),
        sa.Column("due_date", sa.String(), nullable=False),
        sa.Column(
            "priority",
            sa.Enum("high", "medium", "low", name="priority"),
            nullable=False,
        ),
        sa.Column("jira_ticket_id", sa.String(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("open", "in_progress", "done", name="actionitemstatus"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Table 4: chat_sessions
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("meeting_id", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("messages", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_chat_sessions_meeting_id"),
        "chat_sessions",
        ["meeting_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_chat_sessions_user_id"),
        "chat_sessions",
        ["user_id"],
        unique=False,
    )

    # Table 5: decisions
    op.create_table(
        "decisions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("meeting_id", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Table 6: notifications_log
    op.create_table(
        "notifications_log",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("meeting_id", sa.String(), nullable=False),
        sa.Column(
            "type",
            sa.Enum("slack", "email", "jira", "calendar", name="notificationtype"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("pending", "sent", "failed", name="notificationstatus"),
            nullable=False,
        ),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Table 7: participants
    op.create_table(
        "participants",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("meeting_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("speaker_label", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Table 8: processing_jobs
    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("processing", "completed", "failed", name="jobstatus"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("meeting_id", sa.String(), nullable=True),
        sa.Column("completed_nodes", sa.JSON(), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("node_timings", sa.JSON(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("short_summary", sa.Text(), nullable=True),
        sa.Column("action_items_count", sa.Integer(), nullable=True),
        sa.Column("decisions_count", sa.Integer(), nullable=True),
        sa.Column("participants_count", sa.Integer(), nullable=True),
        sa.Column("jira_tickets_created", sa.Integer(), nullable=True),
        sa.Column("calendar_event_id", sa.String(), nullable=True),
        sa.Column("notifications_sent", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("processing_jobs")
    op.drop_table("participants")
    op.drop_table("notifications_log")
    op.drop_table("decisions")
    op.drop_index(op.f("ix_chat_sessions_user_id"), table_name="chat_sessions")
    op.drop_index(op.f("ix_chat_sessions_meeting_id"), table_name="chat_sessions")
    op.drop_table("chat_sessions")
    op.drop_table("action_items")
    op.drop_index(op.f("ix_user_tool_credentials_user_id"), table_name="user_tool_credentials")
    op.drop_index(op.f("ix_user_tool_credentials_tool_name"), table_name="user_tool_credentials")
    op.drop_table("user_tool_credentials")
    op.drop_table("meetings")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
