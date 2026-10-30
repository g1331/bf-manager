"""groups：群组、成员、邀请链接

Revision ID: 20261031_0019
Revises: 20261030_0018
Create Date: 2026-10-31 10:00:00.000000

1. 新表 groups、group_members、group_invites。
2. audit_logs 加 group_id（不设外键，群删了记录还在），群组操作按它筛选。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261031_0019"
down_revision: str | None = "20261030_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _now_col(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.create_table(
        "groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_groups_created_by_users"),
        ),
        _now_col("created_at"),
    )

    op.create_table(
        "group_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("groups.id", ondelete="CASCADE", name="fk_group_members_group_id_groups"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_group_members_user_id_users"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column(
            "invited_by",
            sa.Integer(),
            sa.ForeignKey(
                "users.id", ondelete="SET NULL", name="fk_group_members_invited_by_users"
            ),
        ),
        _now_col("joined_at"),
        sa.UniqueConstraint("group_id", "user_id", name="uq_group_members_group_user"),
    )
    op.create_index("ix_group_members_group_id", "group_members", ["group_id"])
    op.create_index("ix_group_members_user_id", "group_members", ["user_id"])

    op.create_table(
        "group_invites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("groups.id", ondelete="CASCADE", name="fk_group_invites_group_id_groups"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey(
                "users.id", ondelete="SET NULL", name="fk_group_invites_created_by_users"
            ),
        ),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("uses", sa.Integer(), server_default="0", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        _now_col("created_at"),
    )
    op.create_index("ix_group_invites_group_id", "group_invites", ["group_id"])
    op.create_index("ix_group_invites_token_hash", "group_invites", ["token_hash"], unique=True)

    op.add_column("audit_logs", sa.Column("group_id", sa.Integer()))
    op.create_index("ix_audit_logs_group_id", "audit_logs", ["group_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_group_id", table_name="audit_logs")
    op.drop_column("audit_logs", "group_id")
    op.drop_index("ix_group_invites_token_hash", table_name="group_invites")
    op.drop_index("ix_group_invites_group_id", table_name="group_invites")
    op.drop_table("group_invites")
    op.drop_index("ix_group_members_user_id", table_name="group_members")
    op.drop_index("ix_group_members_group_id", table_name="group_members")
    op.drop_table("group_members")
    op.drop_table("groups")
