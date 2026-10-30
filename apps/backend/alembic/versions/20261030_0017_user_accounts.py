"""user_accounts：邮箱密码账号、邮件验证、邀请码

Revision ID: 20261030_0017
Revises: 20261029_0016
Create Date: 2026-10-30 16:00:00.000000

1. users 加 email_verified_at / status / token_version，邮箱按小写部分唯一。
   现有账号：有本地密码的是本地管理员，记 active；其余是 remid 登录自动建的号，记 legacy。
2. ea_bindings 加 ea_user_id / verified_via；persona_id 的唯一约束改为只对未冻结的行生效，
   解绑、改绑后留下的历史行不再占着这个 EA 号。现有行 verified_via 记 legacy。
3. 新表 email_verifications、invite_codes。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261030_0017"
down_revision: str | None = "20261029_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. users
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True)))
    op.add_column(
        "users",
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), server_default="0", nullable=False),
    )
    # 旧版本没有邮箱验证流程，已有的 email（CLI 建管理员时可选填）不算验证过；
    # 统一转小写，免得和新的部分唯一索引冲突
    op.execute("UPDATE users SET email = lower(email) WHERE email IS NOT NULL")
    # 只差大小写的重复邮箱（只可能出自 CLI 手填）保留 id 最小的那个，其余清空，
    # 否则建唯一索引会失败、整个迁移卡住
    op.execute(
        "UPDATE users SET email = NULL WHERE id IN ("
        "  SELECT id FROM ("
        "    SELECT id, row_number() OVER (PARTITION BY email ORDER BY id) AS rn"
        "    FROM users WHERE email IS NOT NULL"
        "  ) dup WHERE dup.rn > 1"
        ")"
    )
    op.execute("UPDATE users SET status = 'legacy' WHERE local_password_hash IS NULL")
    op.create_index(
        "uq_users_email_lower",
        "users",
        [sa.text("lower(email)")],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )

    # 2. ea_bindings
    op.add_column("ea_bindings", sa.Column("ea_user_id", sa.BigInteger()))
    op.add_column("ea_bindings", sa.Column("verified_via", sa.String(16)))
    op.execute("UPDATE ea_bindings SET verified_via = 'legacy'")
    op.drop_constraint("uq_ea_bindings_persona_id", "ea_bindings", type_="unique")
    op.create_index(
        "uq_ea_bindings_persona_active",
        "ea_bindings",
        ["persona_id"],
        unique=True,
        postgresql_where=sa.text("is_frozen = false"),
    )

    # 3. 新表
    op.create_table(
        "email_verifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey(
                "users.id", ondelete="CASCADE", name="fk_email_verifications_user_id_users"
            ),
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("request_ip", sa.String(64)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_email_verifications_email", "email_verifications", ["email"])
    op.create_index(
        "ix_email_verifications_token_hash", "email_verifications", ["token_hash"], unique=True
    )
    op.create_index("ix_email_verifications_user_id", "email_verifications", ["user_id"])

    op.create_table(
        "invite_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_invite_codes_created_by_users"),
        ),
        sa.Column(
            "used_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_invite_codes_used_by_users"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_invite_codes_code", "invite_codes", ["code"], unique=True)
    op.create_index("ix_invite_codes_created_by", "invite_codes", ["created_by"])


def downgrade() -> None:
    op.drop_index("ix_invite_codes_created_by", table_name="invite_codes")
    op.drop_index("ix_invite_codes_code", table_name="invite_codes")
    op.drop_table("invite_codes")
    op.drop_index("ix_email_verifications_user_id", table_name="email_verifications")
    op.drop_index("ix_email_verifications_token_hash", table_name="email_verifications")
    op.drop_index("ix_email_verifications_email", table_name="email_verifications")
    op.drop_table("email_verifications")

    # 降级前每个 persona 只能剩一行，否则恢复全表唯一约束会失败：
    # 有未冻结的行就留它；全是冻结的历史行（绑了又解绑多次）就留 id 最大的那行
    op.execute(
        "DELETE FROM ea_bindings b USING ea_bindings a "
        "WHERE b.persona_id = a.persona_id AND b.id <> a.id AND b.is_frozen = true "
        "AND (a.is_frozen = false OR a.id > b.id)"
    )
    op.drop_index("uq_ea_bindings_persona_active", table_name="ea_bindings")
    op.create_unique_constraint("uq_ea_bindings_persona_id", "ea_bindings", ["persona_id"])
    op.drop_column("ea_bindings", "verified_via")
    op.drop_column("ea_bindings", "ea_user_id")

    op.drop_index("uq_users_email_lower", table_name="users")
    op.drop_column("users", "token_version")
    op.drop_column("users", "status")
    op.drop_column("users", "email_verified_at")
