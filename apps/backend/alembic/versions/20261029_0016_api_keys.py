"""api_keys：开放 API Key

Revision ID: 20261029_0016
Revises: 20261029_0015
Create Date: 2026-10-29 22:00:00.000000

只存 key 的 sha256 和开头几位，明文创建时返回一次。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261029_0016"
down_revision: str | None = "20261029_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "api_keys"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_api_keys_user_id_users"),
            nullable=False,
        ),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("prefix", sa.String(16), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("rate_multiplier", sa.Integer(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_api_keys_user_id", TABLE, ["user_id"])
    op.create_index("ix_api_keys_key_hash", TABLE, ["key_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_api_keys_key_hash", table_name=TABLE)
    op.drop_index("ix_api_keys_user_id", table_name=TABLE)
    op.drop_table(TABLE)
