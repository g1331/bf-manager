"""bf1_server_player_counts: persisted_game_id 换成 server_id

Revision ID: 20261025_0007
Revises: 20261025_0006
Create Date: 2026-10-25 18:00:00.000000

生产快照里没有 PGID，persisted_game_id 列一直为空。改为记录由 gameId 问 Gateway 解析出的
RSP serverId，人数曲线按它跨重启、跨改名归并。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261025_0007"
down_revision: str | None = "20261025_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "bf1_server_player_counts"


def upgrade() -> None:
    op.drop_index("ix_bf1_server_player_counts_persisted_game_id", table_name=TABLE)
    op.drop_column(TABLE, "persisted_game_id")
    op.add_column(TABLE, sa.Column("server_id", sa.BigInteger(), nullable=True))
    op.create_index("ix_bf1_server_player_counts_server_id", TABLE, ["server_id"])


def downgrade() -> None:
    op.drop_index("ix_bf1_server_player_counts_server_id", table_name=TABLE)
    op.drop_column(TABLE, "server_id")
    op.add_column(TABLE, sa.Column("persisted_game_id", sa.String(64), nullable=True))
    op.create_index("ix_bf1_server_player_counts_persisted_game_id", TABLE, ["persisted_game_id"])
