"""add image messages

Revision ID: 0002_message_images
Revises: 0001_initial
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_message_images"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column(
            "message_type",
            sa.String(length=16),
            server_default=sa.text("'text'"),
            nullable=False,
        ),
    )
    op.add_column("messages", sa.Column("image_url", sa.Text(), nullable=True))
    op.add_column("messages", sa.Column("image_mime_type", sa.String(length=64), nullable=True))
    op.add_column("messages", sa.Column("image_size_bytes", sa.Integer(), nullable=True))
    op.create_check_constraint("ck_messages_type", "messages", "message_type IN ('text', 'image')")
    op.create_check_constraint(
        "ck_messages_image_requires_url",
        "messages",
        "message_type != 'image' OR image_url IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_messages_image_requires_url", "messages", type_="check")
    op.drop_constraint("ck_messages_type", "messages", type_="check")
    op.drop_column("messages", "image_size_bytes")
    op.drop_column("messages", "image_mime_type")
    op.drop_column("messages", "image_url")
    op.drop_column("messages", "message_type")
