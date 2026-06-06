"""add ea_accounts.use_count

Revision ID: 20260606_0003
Revises: 20260525_0002
Create Date: 2026-06-06 16:00:00.000000

为 EA 账号池新增累计取用次数列，供运维观察账号负载分布。新列 NOT NULL，
存量行用 server_default 0 回填，建表后保留默认值即可（应用层每次取用自增）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260606_0003"
down_revision: str | None = "20260525_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ea_accounts",
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("ea_accounts", "use_count")
