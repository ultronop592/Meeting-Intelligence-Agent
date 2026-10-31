"""add phase 7 differentiator: commitment_links and decision_contradictions tables

Revision ID: 0009_add_phase7_differentiator
Revises: 0008_add_phase6_chunk_retrieval
Create Date: 2026-10-31

Adds:
- commitment_links table for tracking commitments across meetings (repeated promises, aging, stale status)
- decision_contradictions table for detecting conflicts across architectural/business decisions
- is_repeated_commitment, repeated_from_meeting_id, and days_unresolved columns to action_items
- has_contradiction and contradiction_count columns to decisions
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0009_add_phase7_differentiator"
down_revision: Union[str, None] = "0008_add_phase6_chunk_retrieval"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add Phase 7 columns to action_items
    op.add_column("action_items", sa.Column("is_repeated_commitment", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("action_items", sa.Column("repeated_from_meeting_id", sa.String(), nullable=True))
    op.add_column("action_items", sa.Column("days_unresolved", sa.Integer(), server_default=sa.text("0"), nullable=False))
    op.create_index("ix_action_items_repeated", "action_items", ["is_repeated_commitment"], unique=False)

    # 2. Add Phase 7 columns to decisions
    op.add_column("decisions", sa.Column("has_contradiction", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("decisions", sa.Column("contradiction_count", sa.Integer(), server_default=sa.text("0"), nullable=False))

    # 3. Create commitment_links table
    op.create_table(
        "commitment_links",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("source_action_item_id", sa.String(), sa.ForeignKey("action_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_action_item_id", sa.String(), sa.ForeignKey("action_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_meeting_id", sa.String(), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_meeting_id", sa.String(), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("link_type", sa.String(length=64), server_default=sa.text("'repeated_commitment'"), nullable=False),
        sa.Column("confidence", sa.Float(), server_default=sa.text("1.0"), nullable=False),
        sa.Column("similarity_score", sa.Float(), server_default=sa.text("0.0"), nullable=False),
        sa.Column("days_unresolved", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'open'"), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_commitment_links_pair", "commitment_links", ["source_action_item_id", "target_action_item_id"], unique=False)
    op.create_index("ix_commitment_links_meetings", "commitment_links", ["source_meeting_id", "target_meeting_id"], unique=False)
    op.create_index("ix_commitment_links_status", "commitment_links", ["status"], unique=False)

    # 4. Create decision_contradictions table
    op.create_table(
        "decision_contradictions",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("new_decision_id", sa.String(), sa.ForeignKey("decisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prior_decision_id", sa.String(), sa.ForeignKey("decisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("new_meeting_id", sa.String(), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prior_meeting_id", sa.String(), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contradiction_score", sa.Float(), server_default=sa.text("0.0"), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("resolution_status", sa.String(length=32), server_default=sa.text("'detected'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_decision_contradictions_pair", "decision_contradictions", ["new_decision_id", "prior_decision_id"], unique=False)
    op.create_index("ix_decision_contradictions_status", "decision_contradictions", ["resolution_status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_decision_contradictions_status", table_name="decision_contradictions")
    op.drop_index("ix_decision_contradictions_pair", table_name="decision_contradictions")
    op.drop_table("decision_contradictions")

    op.drop_index("ix_commitment_links_status", table_name="commitment_links")
    op.drop_index("ix_commitment_links_meetings", table_name="commitment_links")
    op.drop_index("ix_commitment_links_pair", table_name="commitment_links")
    op.drop_table("commitment_links")

    op.drop_column("decisions", "contradiction_count")
    op.drop_column("decisions", "has_contradiction")

    op.drop_index("ix_action_items_repeated", table_name="action_items")
    op.drop_column("action_items", "days_unresolved")
    op.drop_column("action_items", "repeated_from_meeting_id")
    op.drop_column("action_items", "is_repeated_commitment")
