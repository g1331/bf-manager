"""site_settings：后台可切换的站点配置（先用于注册方式）

Revision ID: 20261031_0020
Revises: 20261031_0019
Create Date: 2026-10-31 12:00:00.000000

没有这一行时按环境变量 REGISTRATION_INVITE_REQUIRED 推出默认值，所以升级后行为不变。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261031_0020"
down_revision: str | None = "20261031_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "site_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column(
            "updated_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("site_settings")
