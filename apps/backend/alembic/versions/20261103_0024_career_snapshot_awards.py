"""bf1_career_snapshots.awards：对局跟踪的勋带快照

Revision ID: 20261103_0024
Revises: 20261102_0023
Create Date: 2026-11-03 10:00:00.000000

编码见 app/domain/games/bf1/round_awards.py；上线前的行为空，跟踪器第一次见到这个人时读一次。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261103_0024"
down_revision: str | None = "20261102_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bf1_career_snapshots", sa.Column("awards", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("bf1_career_snapshots", "awards")
