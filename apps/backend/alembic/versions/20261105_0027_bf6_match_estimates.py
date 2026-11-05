"""bf6_stat_snapshots / bf6_match_estimates：BF6 对局估算

Revision ID: 20261105_0027
Revises: 20261105_0026
Create Date: 2026-11-05 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261105_0027"
down_revision: str | None = "20261105_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bf6_stat_snapshots",
        sa.Column("nucleus_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("stats", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("polled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_bf6_stat_snapshots_viewed_at", "bf6_stat_snapshots", ["viewed_at"])
    op.create_table(
        "bf6_match_estimates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nucleus_id", sa.BigInteger(), nullable=False),
        sa.Column("started_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("matches", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_bf6_match_estimates_observed_at", "bf6_match_estimates", ["observed_at"])
    op.create_index(
        "ix_bf6_match_estimates_player", "bf6_match_estimates", ["nucleus_id", "observed_at"]
    )


def downgrade() -> None:
    op.drop_table("bf6_match_estimates")
    op.drop_table("bf6_stat_snapshots")
