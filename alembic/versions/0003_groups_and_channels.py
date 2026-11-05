"""add groups and channels

Revision ID: 0003_groups_and_channels
Revises: 0002_message_images
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_groups_and_channels"
down_revision: str | None = "0002_message_images"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chats",
        sa.Column(
            "chat_type",
            sa.String(length=16),
            server_default=sa.text("'direct'"),
            nullable=False,
        ),
    )
    op.add_column("chats", sa.Column("owner_id", sa.Uuid(), nullable=True))
    op.add_column("chats", sa.Column("title", sa.String(length=128), nullable=True))
    op.add_column("chats", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("chats", sa.Column("avatar_url", sa.Text(), nullable=True))
    op.add_column(
        "chats",
        sa.Column(
            "is_public",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.alter_column("chats", "user1_id", existing_type=sa.Uuid(), nullable=True)
    op.alter_column("chats", "user2_id", existing_type=sa.Uuid(), nullable=True)

    op.create_check_constraint(
        "ck_chats_type", "chats", "chat_type IN ('direct', 'group', 'channel')"
    )
    op.create_check_constraint(
        "ck_chats_shape",
        "chats",
        "(chat_type = 'direct' AND user1_id IS NOT NULL AND user2_id IS NOT NULL"
        " AND owner_id IS NULL)"
        " OR (chat_type <> 'direct' AND user1_id IS NULL AND user2_id IS NULL"
        " AND owner_id IS NOT NULL AND title IS NOT NULL)",
    )
    op.create_foreign_key(
        "fk_chats_owner_id_users",
        "chats",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_chats_chat_type", "chats", ["chat_type"])
    op.create_index("ix_chats_owner_id", "chats", ["owner_id"])

    op.create_table(
        "chat_members",
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            sa.String(length=16),
            server_default=sa.text("'member'"),
            nullable=False,
        ),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("role IN ('owner', 'admin', 'member')", name="ck_chat_members_role"),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("chat_id", "user_id"),
    )
    op.create_index("ix_chat_members_user_id", "chat_members", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_members_user_id", table_name="chat_members")
    op.drop_table("chat_members")

    op.drop_index("ix_chats_owner_id", table_name="chats")
    op.drop_index("ix_chats_chat_type", table_name="chats")
    op.drop_constraint("fk_chats_owner_id_users", "chats", type_="foreignkey")
    op.drop_constraint("ck_chats_shape", "chats", type_="check")
    op.drop_constraint("ck_chats_type", "chats", type_="check")

    op.execute("DELETE FROM chats WHERE chat_type <> 'direct'")
    op.alter_column("chats", "user1_id", existing_type=sa.Uuid(), nullable=False)
    op.alter_column("chats", "user2_id", existing_type=sa.Uuid(), nullable=False)

    op.drop_column("chats", "is_public")
    op.drop_column("chats", "avatar_url")
    op.drop_column("chats", "description")
    op.drop_column("chats", "title")
    op.drop_column("chats", "owner_id")
    op.drop_column("chats", "chat_type")
