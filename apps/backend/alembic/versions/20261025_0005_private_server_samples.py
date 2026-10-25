"""bf1_server_player_counts: 改为全量私服采样

Revision ID: 20261025_0005
Revises: 20260627_0004
Create Date: 2026-10-25 12:00:00.000000

原表按 servers 登记表外键记点，服务器重启换 gameId 后就对不上，生产上一直是空表。
改为直接记录快照里的所有私服：去掉 server_pk 外键，新增 game_id / name / map_name /
game_mode。表里没有数据，直接重建。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261025_0005"
down_revision: str | None = "20260627_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "bf1_server_player_counts"


def _counts_and_time() -> list[sa.Column]:
    return [
        sa.Column("player_count", sa.Integer(), nullable=False),
        sa.Column("queue_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("spectator_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_player_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "sampled_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.drop_table(TABLE)
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("map_name", sa.String(64), nullable=True),
        sa.Column("game_mode", sa.String(32), nullable=True),
        *_counts_and_time(),
        sa.PrimaryKeyConstraint("id", name="pk_bf1_server_player_counts"),
    )
    op.create_index("ix_bf1_server_player_counts_game_id", TABLE, ["game_id"])
    op.create_index("ix_bf1_server_player_counts_sampled_at", TABLE, ["sampled_at"])
    op.create_index("ix_bf1_server_player_counts_name_time", TABLE, ["name", "sampled_at"])


def downgrade() -> None:
    op.drop_table(TABLE)
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("server_pk", sa.Integer(), nullable=False),
        *_counts_and_time(),
        sa.ForeignKeyConstraint(
            ["server_pk"],
            ["servers.id"],
            ondelete="CASCADE",
            name="fk_bf1_server_player_counts_server_pk_servers",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_bf1_server_player_counts"),
    )
    op.create_index("ix_bf1_server_player_counts_server_time", TABLE, ["server_pk", "sampled_at"])
