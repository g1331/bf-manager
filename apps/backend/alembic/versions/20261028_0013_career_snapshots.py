"""bf1_career_snapshots：每人最近一次读到的完整生涯，对局跟踪读武器载具时沿用

Revision ID: 20261028_0013
Revises: 20261027_0012
Create Date: 2026-10-28 12:00:00.000000

每人一行：核心向量（varint）和武器载具快照（编码见 app/domain/games/bf1/round_weapons.py），
按 updated_at 保留 14 天。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261028_0013"
down_revision: str | None = "20261027_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bf1_career_snapshots",
        sa.Column("pid", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("core", sa.LargeBinary(), nullable=False),
        sa.Column("weapons", sa.LargeBinary(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_bf1_career_snapshots_updated_at", "bf1_career_snapshots", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_bf1_career_snapshots_updated_at", table_name="bf1_career_snapshots")
    op.drop_table("bf1_career_snapshots")
