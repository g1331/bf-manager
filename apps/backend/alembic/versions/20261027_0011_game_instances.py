"""bf1_game_instances：服务器实例登记，人数点去掉 server_id / name

Revision ID: 20261027_0011
Revises: 20261026_0010
Create Date: 2026-10-27 20:00:00.000000

gameId 只在一次开服期间不变。人数点和名单继续按它写，服名与 RSP serverId 挪到实例表，每个
实例一行，读时按 serverId 把重启前后的实例归并，不再在每个采样点上重复存服名，也不再按服名
猜归属。实例从现有人数点回填：serverId 取各 gameId 解析到的值，服名取最后一个点上的。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261027_0011"
down_revision: str | None = "20261026_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COUNTS = "bf1_server_player_counts"
INSTANCES = "bf1_game_instances"


def upgrade() -> None:
    op.create_table(
        INSTANCES,
        sa.Column("game_id", sa.BigInteger(), primary_key=True),
        sa.Column("server_id", sa.BigInteger(), nullable=True),
        sa.Column("official", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_bf1_game_instances_server_id", INSTANCES, ["server_id"])
    op.execute(
        """
        INSERT INTO bf1_game_instances (game_id, server_id, official, name, first_seen, last_seen)
        SELECT g.game_id, g.server_id, false,
               (SELECT c.name FROM bf1_server_player_counts c WHERE c.game_id = g.game_id
                ORDER BY c.sampled_at DESC LIMIT 1),
               g.first_seen, g.last_seen
        FROM (
            SELECT game_id, max(server_id) AS server_id,
                   min(sampled_at) AS first_seen, max(sampled_at) AS last_seen
            FROM bf1_server_player_counts GROUP BY game_id
        ) g
        """
    )
    op.drop_index("ix_bf1_server_player_counts_name_time", table_name=COUNTS)
    op.drop_index("ix_bf1_server_player_counts_server_id", table_name=COUNTS)
    op.drop_column(COUNTS, "server_id")
    op.drop_column(COUNTS, "name")


def downgrade() -> None:
    op.add_column(COUNTS, sa.Column("name", sa.String(255), nullable=True))
    op.add_column(COUNTS, sa.Column("server_id", sa.BigInteger(), nullable=True))
    op.execute(
        """
        UPDATE bf1_server_player_counts SET
            name = COALESCE(
                (SELECT i.name FROM bf1_game_instances i
                 WHERE i.game_id = bf1_server_player_counts.game_id), ''
            ),
            server_id = (SELECT i.server_id FROM bf1_game_instances i
                         WHERE i.game_id = bf1_server_player_counts.game_id)
        """
    )
    op.alter_column(COUNTS, "name", nullable=False)
    op.create_index("ix_bf1_server_player_counts_server_id", COUNTS, ["server_id"])
    op.create_index("ix_bf1_server_player_counts_name_time", COUNTS, ["name", "sampled_at"])
    op.drop_index("ix_bf1_game_instances_server_id", table_name=INSTANCES)
    op.drop_table(INSTANCES)
