"""user_freeze：冻结账号的时间、原因和操作人

Revision ID: 20261101_0022
Revises: 20261031_0021
Create Date: 2026-11-01 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261101_0022"
down_revision: str | None = "20261031_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("frozen_reason", sa.String(200), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "frozen_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_users_frozen_by_users"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_frozen_by_users", "users", type_="foreignkey")
    op.drop_column("users", "frozen_by")
    op.drop_column("users", "frozen_reason")
    op.drop_column("users", "frozen_at")
