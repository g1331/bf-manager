"""bf1_card_jobs：一键卡行动 / 手动锚定任务

Revision ID: 20261029_0014
Revises: 20261028_0013
Create Date: 2026-10-29 12:00:00.000000

服主凭据只在任务协程内存里，不落库；开始前的设置快照含服务器密码，加密存放。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261029_0014"
down_revision: str | None = "20261028_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "bf1_card_jobs"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("game_id", sa.BigInteger(), nullable=False),
        sa.Column("server_id", sa.BigInteger(), nullable=False),
        sa.Column("server_name", sa.String(128), nullable=False, server_default=""),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_bf1_card_jobs_user_id_users"),
            nullable=True,
        ),
        sa.Column("persona_id", sa.BigInteger(), nullable=False),
        sa.Column("persona_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("client_ip", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("snapshot_enc", sa.Text(), nullable=True),
        sa.Column("result_maps", sa.JSON(), nullable=True),
        sa.Column("message", sa.String(256), nullable=False, server_default=""),
        sa.Column("events", sa.JSON(), nullable=False),
        sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_bf1_card_jobs_game_id", TABLE, ["game_id"])
    op.create_index("ix_bf1_card_jobs_status", TABLE, ["status"])


def downgrade() -> None:
    op.drop_index("ix_bf1_card_jobs_status", table_name=TABLE)
    op.drop_index("ix_bf1_card_jobs_game_id", table_name=TABLE)
    op.drop_table(TABLE)
