"""account_deletion：用户申请注销后的计划删除时间

Revision ID: 20261102_0023
Revises: 20261101_0022
Create Date: 2026-11-02 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261102_0023"
down_revision: str | None = "20261101_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("deletion_scheduled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index("ix_users_deletion_scheduled_at", "users", ["deletion_scheduled_at"])


def downgrade() -> None:
    op.drop_index("ix_users_deletion_scheduled_at", table_name="users")
    op.drop_column("users", "deletion_scheduled_at")
