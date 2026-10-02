"""add transcript_words column to meetings table

Revision ID: 0004_add_transcript_words
Revises: 0003_add_perf_indexes
Create Date: 2026-10-02 11:55:00.000000

Adds transcript_words JSON column to meetings table to store word-accurate
subtitle and playback synchronization timing from Groq Whisper.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "0004_add_transcript_words"
down_revision: Union[str, None] = "0003_add_perf_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "meetings",
        sa.Column("transcript_words", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("meetings", "transcript_words")
