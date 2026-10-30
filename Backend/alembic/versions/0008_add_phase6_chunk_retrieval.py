"""add phase 6 chunk-level retrieval: transcript_chunks table with pgvector and full-text search

Revision ID: 0008_add_phase6_chunk_retrieval
Revises: 0007_add_phase3_durable_runtime
Create Date: 2026-10-30

Adds:
- transcript_chunks table (chunk_index, start_sec, end_sec, speaker, text, embedding vector(768))
- GIN tsvector index on text for Postgres full-text search
- IVFFlat pgvector index on embedding for ANN similarity search
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0008_add_phase6_chunk_retrieval"
down_revision: Union[str, None] = "0007_add_phase3_durable_runtime"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "transcript_chunks",
        sa.Column("id",          sa.String(),  primary_key=True, nullable=False),
        sa.Column("meeting_id",  sa.String(),  sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("start_sec",   sa.Float(),   nullable=False),
        sa.Column("end_sec",     sa.Float(),   nullable=False),
        sa.Column("speaker",     sa.String(128), nullable=True),
        sa.Column("text",        sa.Text(),    nullable=False),
        sa.Column("embedding",   sa.Text(),    nullable=True),   # pgvector vector(768); altered below
        sa.Column("created_at",  sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Composite indexes
    op.create_index("ix_transcript_chunks_meeting_idx",  "transcript_chunks", ["meeting_id", "chunk_index"])
    op.create_index("ix_transcript_chunks_meeting_time", "transcript_chunks", ["meeting_id", "start_sec"])

    # Full-text search: generated tsvector column + GIN index (Postgres 12+)
    op.execute(
        "ALTER TABLE transcript_chunks "
        "ADD COLUMN text_tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('english', coalesce(text,''))) STORED"
    )
    op.execute("CREATE INDEX ix_transcript_chunks_tsv ON transcript_chunks USING GIN (text_tsv)")

    # pgvector IVFFlat index — created after data is loaded; safe to create empty
    # NOTE: requires `CREATE EXTENSION IF NOT EXISTS vector;` to already exist (done in migration 0001 or earlier)
    op.execute(
        "ALTER TABLE transcript_chunks "
        "ALTER COLUMN embedding TYPE vector(768) USING embedding::vector"
    )
    # IVFFlat index will be created once rows exist; add here as a deferred best-effort
    op.execute(
        "DO $$ BEGIN "
        "  IF (SELECT count(*) FROM transcript_chunks) >= 100 THEN "
        "    CREATE INDEX ix_transcript_chunks_embedding ON transcript_chunks "
        "    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50); "
        "  END IF; "
        "END $$"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_transcript_chunks_embedding")
    op.execute("DROP INDEX IF EXISTS ix_transcript_chunks_tsv")
    op.drop_index("ix_transcript_chunks_meeting_time", table_name="transcript_chunks")
    op.drop_index("ix_transcript_chunks_meeting_idx",  table_name="transcript_chunks")
    op.drop_table("transcript_chunks")
