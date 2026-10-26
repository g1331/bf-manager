"""bf1 私服名单时间线：bf1_server_player_days + bf1_player_names，人数点加进出人数

Revision ID: 20261026_0010
Revises: 20261025_0009
Create Date: 2026-10-26 14:00:00.000000

名单按「每人每服每天一行、事件追加在行内」存，换队、短时离开再回来都不新增行；
名字单独一张表。人数点的 joined_count / left_count 为空表示那一轮没拿到名单。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261026_0010"
down_revision: str | None = "20261025_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COUNTS = "bf1_server_player_counts"


def upgrade() -> None:
    op.create_table(
        "bf1_server_player_days",
        sa.Column("game_id", sa.BigInteger(), primary_key=True),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("pid", sa.BigInteger(), primary_key=True),
        sa.Column("events", sa.Text(), nullable=False),
    )
    if op.get_bind().dialect.name == "postgresql":
        # 每分钟几百次追加；留页内余量让更新走 HOT，不随更新膨胀
        op.execute("ALTER TABLE bf1_server_player_days SET (fillfactor = 80)")
    op.create_table(
        "bf1_player_names",
        sa.Column("pid", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column(COUNTS, sa.Column("joined_count", sa.SmallInteger(), nullable=True))
    op.add_column(COUNTS, sa.Column("left_count", sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column(COUNTS, "left_count")
    op.drop_column(COUNTS, "joined_count")
    op.drop_table("bf1_player_names")
    op.drop_table("bf1_server_player_days")
