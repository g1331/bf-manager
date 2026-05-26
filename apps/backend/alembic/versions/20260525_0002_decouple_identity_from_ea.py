"""decouple identity from ea: split users into users + ea_bindings

Revision ID: 20260525_0002
Revises: 20260524_0001
Create Date: 2026-05-25 21:00:00.000000

数据搬运策略：
1. 预检查 users.persona_id 重复或异常值，发现立即报错退出
2. 建 ea_bindings 表（含 persona_id UNIQUE + partial unique index 兜底 is_primary 唯一性）
3. users 表新增 username/local_password_hash/email/is_frozen 列（先 nullable）
4. 把现有 users 的 persona/encrypted/display/avatar 字段复制为一条 primary binding
5. 用 persona_<id> 回填 users.username，置 NOT NULL + UNIQUE
6. 删除 users 表旧列

admin 名单不在迁移内 seed。部署者升级后手工跑 `python -m app.cli grant-admin --persona <id>`。

down 行为：若发现 user 无任何 binding（CLI 创建的本地 admin），报错退出而非静默删除。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260525_0002"
down_revision: str | None = "20260524_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    # ===== 1. 预检查 users.persona_id 是否存在重复或 NULL =====
    bad = bind.execute(
        sa.text(
            "SELECT persona_id, COUNT(*) AS c FROM users "
            "GROUP BY persona_id HAVING COUNT(*) > 1 OR persona_id IS NULL"
        )
    ).fetchall()
    if bad:
        raise RuntimeError(
            f"users.persona_id 存在重复或 NULL 行（共 {len(bad)} 组），"
            "请先手工清理再执行迁移。冲突样本：" + ", ".join(str(row) for row in bad[:10])
        )

    # ===== 2. 建 ea_bindings 表 =====
    op.create_table(
        "ea_bindings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("persona_id", sa.BigInteger(), nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=True),
        sa.Column("avatar_url", sa.String(length=512), nullable=True),
        sa.Column("encrypted_remid", sa.Text(), nullable=True),
        sa.Column("encrypted_sid", sa.Text(), nullable=True),
        sa.Column("encrypted_session", sa.Text(), nullable=True),
        sa.Column("encrypted_access_token", sa.Text(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_frozen", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_ea_bindings_user_id_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ea_bindings"),
        sa.UniqueConstraint("persona_id", name="uq_ea_bindings_persona_id"),
    )
    op.create_index("ix_ea_bindings_user_id", "ea_bindings", ["user_id"])
    op.create_index("ix_ea_bindings_persona_id", "ea_bindings", ["persona_id"])
    # partial unique index：一个 user 至多一条 primary binding
    op.create_index(
        "uq_ea_bindings_user_primary",
        "ea_bindings",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_primary = true"),
    )

    # ===== 3. users 表新增列（先 nullable） =====
    op.add_column("users", sa.Column("username", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("local_password_hash", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("email", sa.String(length=255), nullable=True))
    op.add_column(
        "users",
        sa.Column("is_frozen", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # ===== 4. 数据搬运：每个 user 一条 primary binding =====
    op.execute(
        sa.text(
            """
            INSERT INTO ea_bindings (
                user_id, persona_id, display_name, avatar_url,
                encrypted_remid, encrypted_sid, encrypted_session, encrypted_access_token,
                is_primary, is_frozen, last_verified_at, created_at, updated_at
            )
            SELECT
                id, persona_id, display_name, avatar_url,
                encrypted_remid, encrypted_sid, encrypted_session, encrypted_access_token,
                true, false, last_login_at, created_at, updated_at
            FROM users
            """
        )
    )

    # ===== 5. 回填 username = persona_<persona_id> =====
    op.execute(
        sa.text("UPDATE users SET username = 'persona_' || persona_id::text WHERE username IS NULL")
    )
    op.alter_column("users", "username", nullable=False)
    op.create_unique_constraint("uq_users_username", "users", ["username"])
    op.create_index("ix_users_username", "users", ["username"])

    # ===== 6. 删除 users 表旧列与对应索引/约束 =====
    op.drop_index("ix_users_persona_id", table_name="users")
    op.drop_constraint("uq_users_persona_id", "users", type_="unique")
    op.drop_column("users", "encrypted_access_token")
    op.drop_column("users", "encrypted_session")
    op.drop_column("users", "encrypted_sid")
    op.drop_column("users", "encrypted_remid")
    op.drop_column("users", "avatar_url")
    op.drop_column("users", "display_name")
    op.drop_column("users", "persona_id")


def downgrade() -> None:
    bind = op.get_bind()

    # ===== 预检查：若存在无 binding 的 user，报错退出 =====
    orphans = bind.execute(
        sa.text(
            "SELECT u.id, u.username FROM users u "
            "LEFT JOIN ea_bindings b ON b.user_id = u.id "
            "GROUP BY u.id, u.username HAVING COUNT(b.id) = 0"
        )
    ).fetchall()
    if orphans:
        raise RuntimeError(
            f"存在 {len(orphans)} 个 user 无任何 ea_bindings（多为 CLI 创建的本地 admin）。"
            "down revision 不会静默删除这些 user。请先手工删除后再回滚。冲突样本："
            + ", ".join(f"id={row[0]} username={row[1]}" for row in orphans[:10])
        )

    # 1. users 表重建旧列（先 nullable，待回填后置 NOT NULL）
    op.add_column("users", sa.Column("persona_id", sa.BigInteger(), nullable=True))
    op.add_column("users", sa.Column("display_name", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("avatar_url", sa.String(length=512), nullable=True))
    op.add_column("users", sa.Column("encrypted_remid", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("encrypted_sid", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("encrypted_session", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("encrypted_access_token", sa.Text(), nullable=True))

    # 2. 从 primary binding 反向拷回
    op.execute(
        sa.text(
            """
            UPDATE users u SET
                persona_id = b.persona_id,
                display_name = b.display_name,
                avatar_url = b.avatar_url,
                encrypted_remid = b.encrypted_remid,
                encrypted_sid = b.encrypted_sid,
                encrypted_session = b.encrypted_session,
                encrypted_access_token = b.encrypted_access_token
            FROM ea_bindings b
            WHERE b.user_id = u.id AND b.is_primary = true
            """
        )
    )

    # 3. persona_id 置 NOT NULL + UNIQUE + index
    op.alter_column("users", "persona_id", nullable=False)
    op.create_unique_constraint("uq_users_persona_id", "users", ["persona_id"])
    op.create_index("ix_users_persona_id", "users", ["persona_id"])

    # 4. 删除新列与 username 约束
    op.drop_index("ix_users_username", table_name="users")
    op.drop_constraint("uq_users_username", "users", type_="unique")
    op.drop_column("users", "is_frozen")
    op.drop_column("users", "email")
    op.drop_column("users", "local_password_hash")
    op.drop_column("users", "username")

    # 5. 删 ea_bindings 表
    op.drop_index("uq_ea_bindings_user_primary", table_name="ea_bindings")
    op.drop_index("ix_ea_bindings_persona_id", table_name="ea_bindings")
    op.drop_index("ix_ea_bindings_user_id", table_name="ea_bindings")
    op.drop_table("ea_bindings")
