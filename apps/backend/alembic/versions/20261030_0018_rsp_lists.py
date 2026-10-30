"""bf1_rsp_servers / bf1_rsp_members：私服名单，供按玩家反查（天眼查）

Revision ID: 20261030_0018
Revises: 20261030_0017
Create Date: 2026-10-30 18:00:00.000000

快照解析 serverId 时顺带存下 getFullServerDetails 里的服主 / 管理 / VIP / 封禁名单，
之后按间隔轮流刷新。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261030_0018"
down_revision: str | None = "20261030_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bf1_rsp_servers",
        sa.Column("server_id", sa.BigInteger(), primary_key=True),
        sa.Column("game_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_bf1_rsp_servers_refreshed_at", "bf1_rsp_servers", ["refreshed_at"])
    op.create_table(
        "bf1_rsp_members",
        sa.Column(
            "server_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "bf1_rsp_servers.server_id",
                ondelete="CASCADE",
                name="fk_bf1_rsp_members_server_id_bf1_rsp_servers",
            ),
            primary_key=True,
        ),
        sa.Column("role", sa.String(8), primary_key=True),
        sa.Column("pid", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=True),
    )
    op.create_index("ix_bf1_rsp_members_pid", "bf1_rsp_members", ["pid"])


def downgrade() -> None:
    op.drop_index("ix_bf1_rsp_members_pid", table_name="bf1_rsp_members")
    op.drop_table("bf1_rsp_members")
    op.drop_index("ix_bf1_rsp_servers_refreshed_at", table_name="bf1_rsp_servers")
    op.drop_table("bf1_rsp_servers")
