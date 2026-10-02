"""add public share links to meetings

Revision ID: 0005_add_public_share_links
Revises: 0004_add_transcript_words
Create Date: 2026-10-02 18:40:00.000000

Adds share_token, share_token_expires_at, and is_publicly_shared columns to
meetings table to support unauthenticated public share links.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "0005_add_public_share_links"
down_revision: Union[str, None] = "0004_add_transcript_words"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "meetings",
        sa.Column("share_token", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_meetings_share_token", "meetings", ["share_token"], unique=True)
    op.add_column(
        "meetings",
        sa.Column("share_token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "meetings",
        sa.Column("is_publicly_shared", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("meetings", "is_publicly_shared")
    op.drop_column("meetings", "share_token_expires_at")
    op.drop_index("ix_meetings_share_token", table_name="meetings")
    op.drop_column("meetings", "share_token")
