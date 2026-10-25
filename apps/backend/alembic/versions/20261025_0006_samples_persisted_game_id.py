"""bf1_server_player_counts.persisted_game_id

Revision ID: 20261025_0006
Revises: 20261025_0005
Create Date: 2026-10-25 15:00:00.000000

记录快照里的 PGID（persistedGameId，服务器重启不变），人数曲线优先按它跨重启归并。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261025_0006"
down_revision: str | None = "20261025_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "bf1_server_player_counts"
INDEX = "ix_bf1_server_player_counts_persisted_game_id"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("persisted_game_id", sa.String(64), nullable=True))
    op.create_index(INDEX, TABLE, ["persisted_game_id"])


def downgrade() -> None:
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_column(TABLE, "persisted_game_id")
