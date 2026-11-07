"""add audio and video note messages

Revision ID: 0004_audio_and_video_messages
Revises: 0003_groups_and_channels
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_audio_and_video_messages"
down_revision: str | None = "0003_groups_and_channels"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_messages_type", "messages", type_="check")
    op.create_check_constraint(
        "ck_messages_type",
        "messages",
        "message_type IN ('text', 'image', 'audio', 'video_note')",
    )

    op.add_column("messages", sa.Column("media_url", sa.Text(), nullable=True))
    op.add_column("messages", sa.Column("media_mime_type", sa.String(length=64), nullable=True))
    op.add_column("messages", sa.Column("media_size_bytes", sa.Integer(), nullable=True))
    op.add_column(
        "messages", sa.Column("media_duration_seconds", sa.Integer(), nullable=True)
    )
    op.create_check_constraint(
        "ck_messages_media_requires_url",
        "messages",
        "message_type NOT IN ('audio', 'video_note') OR media_url IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_messages_media_requires_url", "messages", type_="check")
    op.drop_column("messages", "media_duration_seconds")
    op.drop_column("messages", "media_size_bytes")
    op.drop_column("messages", "media_mime_type")
    op.drop_column("messages", "media_url")

    op.execute("DELETE FROM messages WHERE message_type IN ('audio', 'video_note')")
    op.drop_constraint("ck_messages_type", "messages", type_="check")
    op.create_check_constraint(
        "ck_messages_type",
        "messages",
        "message_type IN ('text', 'image')",
    )
