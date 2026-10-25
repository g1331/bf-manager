"""bf1_auto_switches: 行动服自动换图的编排与状态

Revision ID: 20261025_0009
Revises: 20261025_0008
Create Date: 2026-10-25 21:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261025_0009"
down_revision: str | None = "20261025_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "bf1_auto_switches"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("game_id", sa.BigInteger(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("events", sa.JSON(), nullable=False),
        sa.Column(
            "enabled_by_user_id",
            sa.Integer(),
            sa.ForeignKey(
                "users.id",
                ondelete="SET NULL",
                name="fk_bf1_auto_switches_enabled_by_user_id_users",
            ),
            nullable=True,
        ),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_bf1_auto_switches_game_id", TABLE, ["game_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_bf1_auto_switches_game_id", table_name=TABLE)
    op.drop_table(TABLE)
