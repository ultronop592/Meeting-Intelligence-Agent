"""add audio_storage_key to meetings

Revision ID: 0002_add_audio_storage_key
Revises: 0001_initial_schema
Create Date: 2026-10-01 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002_add_audio_storage_key"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "meetings",
        sa.Column("audio_storage_key", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("meetings", "audio_storage_key")
