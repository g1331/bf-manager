"""bf1_exchange_snapshots: 交换每期快照

Revision ID: 20261025_0008
Revises: 20261025_0007
Create Date: 2026-10-25 20:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261025_0008"
down_revision: str | None = "20261025_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "bf1_exchange_snapshots"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
    )
    op.create_index("ix_bf1_exchange_snapshots_captured_at", TABLE, ["captured_at"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_bf1_exchange_snapshots_captured_at", table_name=TABLE)
    op.drop_table(TABLE)
