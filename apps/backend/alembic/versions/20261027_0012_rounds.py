"""bf1_rounds + bf1_player_round_days：生涯差分算出的每局战绩

Revision ID: 20261027_0012
Revises: 20261027_0011
Create Date: 2026-10-27 22:00:00.000000

每局一行，参与者 pid 排序后存差值 varint；每人每天一行，各局战绩条目（只存非零项的稀疏 varint）
首尾相接追加在 data 里。编码见 app/domain/games/bf1/round_stats.py。保留 90 天。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261027_0012"
down_revision: str | None = "20261027_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bf1_rounds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("game_id", sa.BigInteger(), nullable=False),
        sa.Column("map_name", sa.String(64), nullable=True),
        sa.Column("game_mode", sa.String(32), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_start", sa.Boolean(), nullable=False),
        sa.Column("settled", sa.Boolean(), nullable=False),
        sa.Column("winner", sa.SmallInteger(), nullable=True),
        sa.Column("player_count", sa.SmallInteger(), nullable=False),
        sa.Column("pids", sa.LargeBinary(), nullable=False),
    )
    op.create_index("ix_bf1_rounds_ended_at", "bf1_rounds", ["ended_at"])
    op.create_index("ix_bf1_rounds_game_ended", "bf1_rounds", ["game_id", "ended_at"])
    op.create_table(
        "bf1_player_round_days",
        sa.Column("pid", sa.BigInteger(), primary_key=True),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("data", sa.LargeBinary(), nullable=False),
    )
    if op.get_bind().dialect.name == "postgresql":
        # 每局结束时给每个参与者追加一条，留页内余量让更新走 HOT
        op.execute("ALTER TABLE bf1_player_round_days SET (fillfactor = 80)")


def downgrade() -> None:
    op.drop_table("bf1_player_round_days")
    op.drop_index("ix_bf1_rounds_game_ended", table_name="bf1_rounds")
    op.drop_index("ix_bf1_rounds_ended_at", table_name="bf1_rounds")
    op.drop_table("bf1_rounds")
