"""add verification and evidence fields to action items and decisions

Revision ID: 0006_add_verification_and_evidence_fields
Revises: 0005_add_public_share_links
Create Date: 2026-10-24 12:00:00.000000

Adds evidence_quote, evidence_timestamp, confidence, needs_review,
owner_status, and verification_reasoning to action_items and decisions tables.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "0006_add_verification_and_evidence_fields"
down_revision: Union[str, None] = "0005_add_public_share_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Action Items additions
    op.add_column("action_items", sa.Column("evidence_quote", sa.Text(), nullable=True))
    op.add_column("action_items", sa.Column("evidence_timestamp", sa.String(length=32), nullable=True))
    op.add_column("action_items", sa.Column("confidence", sa.Float(), server_default=sa.text("1.0"), nullable=False))
    op.add_column("action_items", sa.Column("needs_review", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("action_items", sa.Column("owner_status", sa.String(length=32), server_default=sa.text("'stated'"), nullable=False))
    op.add_column("action_items", sa.Column("verification_reasoning", sa.Text(), nullable=True))
    op.create_index("ix_action_items_needs_review", "action_items", ["meeting_id", "needs_review"], unique=False)

    # 2. Decisions additions
    op.add_column("decisions", sa.Column("evidence_quote", sa.Text(), nullable=True))
    op.add_column("decisions", sa.Column("evidence_timestamp", sa.String(length=32), nullable=True))
    op.add_column("decisions", sa.Column("confidence", sa.Float(), server_default=sa.text("1.0"), nullable=False))
    op.add_column("decisions", sa.Column("needs_review", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("decisions", sa.Column("verification_reasoning", sa.Text(), nullable=True))


def downgrade() -> None:
    # Decisions rollback
    op.drop_column("decisions", "verification_reasoning")
    op.drop_column("decisions", "needs_review")
    op.drop_column("decisions", "confidence")
    op.drop_column("decisions", "evidence_timestamp")
    op.drop_column("decisions", "evidence_quote")

    # Action Items rollback
    op.drop_index("ix_action_items_needs_review", table_name="action_items")
    op.drop_column("action_items", "verification_reasoning")
    op.drop_column("action_items", "owner_status")
    op.drop_column("action_items", "needs_review")
    op.drop_column("action_items", "confidence")
    op.drop_column("action_items", "evidence_timestamp")
    op.drop_column("action_items", "evidence_quote")
