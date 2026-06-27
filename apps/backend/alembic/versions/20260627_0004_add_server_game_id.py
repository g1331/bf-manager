"""add servers.game_id

Revision ID: 20260627_0004
Revises: 20260606_0003
Create Date: 2026-06-27 12:00:00.000000

为 servers 表新增末次解析到的 EA gameId 列。鉴权与成员关系仍以稳定的 server_id 为准，
该列仅用于「我的服务器」列表生成可点击链接（gameId 随服务器重启而变，访问时回填）。
存量行回填 NULL，下次识别到服主/管理员时由应用层更新。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260627_0004"
down_revision: str | None = "20260606_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("servers", sa.Column("game_id", sa.BigInteger(), nullable=True))
    op.create_index("ix_servers_game_id", "servers", ["game_id"])


def downgrade() -> None:
    op.drop_index("ix_servers_game_id", table_name="servers")
    op.drop_column("servers", "game_id")
