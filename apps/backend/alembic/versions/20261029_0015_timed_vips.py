"""bf1_server_vips: 计时 VIP 与行动服待生效队列

初始迁移就建了这张表但一直没用，这里补上状态、待生效剩余时长、排队时间、授予人和
到期下 V 的退避字段。

Revision ID: 20261029_0015
Revises: 20261029_0014
Create Date: 2026-10-29 22:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261029_0015"
down_revision: str | None = "20261029_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "bf1_server_vips"
FK_GRANTED_BY = "fk_bf1_server_vips_granted_by_user_id_users"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
    )
    op.add_column(TABLE, sa.Column("remaining_seconds", sa.BigInteger(), nullable=True))
    op.add_column(TABLE, sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(TABLE, sa.Column("granted_by_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        FK_GRANTED_BY, TABLE, "users", ["granted_by_user_id"], ["id"], ondelete="SET NULL"
    )
    op.add_column(TABLE, sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(TABLE, sa.Column("last_error", sa.Text(), nullable=True))
    op.add_column(TABLE, sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_bf1_server_vips_expires_at", TABLE, ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_bf1_server_vips_expires_at", table_name=TABLE)
    op.drop_column(TABLE, "last_attempt_at")
    op.drop_column(TABLE, "last_error")
    op.drop_column(TABLE, "attempts")
    op.drop_constraint(FK_GRANTED_BY, TABLE, type_="foreignkey")
    op.drop_column(TABLE, "granted_by_user_id")
    op.drop_column(TABLE, "queued_at")
    op.drop_column(TABLE, "remaining_seconds")
    op.drop_column(TABLE, "status")
