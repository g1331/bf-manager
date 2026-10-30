"""alembic 迁移回环验证断言

在 CI 跑完 `alembic upgrade head`（即应用 20260525_0002）之后调用，
验证数据搬运正确：
1. ea_bindings 表有 3 条记录，全部 is_primary=true / is_frozen=false
2. 凭据字段从 users 完整搬到 ea_bindings
3. users.username 已回填为 persona_<id>
4. users.persona_id 等旧列已被删除
5. server_memberships.user_id 仍指向同一 user（PK 不变）

如果在 downgrade -1 之后调用（带 --post-downgrade 参数），则反向断言：
旧 users 表字段被正确从 primary binding 拷回，ea_bindings 表已删除。
"""

from __future__ import annotations

import asyncio
import sys

from app.core.config import get_settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def assert_upgraded() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, future=True)

    async with engine.connect() as conn:
        # 1. ea_bindings 表 3 条 primary binding
        rows = (await conn.execute(text("SELECT COUNT(*) FROM ea_bindings"))).scalar_one()
        assert rows == 3, f"expected 3 bindings, got {rows}"

        primary_count = (
            await conn.execute(text("SELECT COUNT(*) FROM ea_bindings WHERE is_primary"))
        ).scalar_one()
        assert primary_count == 3, f"expected 3 primary bindings, got {primary_count}"

        # 2. 凭据搬运正确
        creds = (
            await conn.execute(
                text(
                    "SELECT encrypted_remid, encrypted_sid, encrypted_session, encrypted_access_token "
                    "FROM ea_bindings WHERE persona_id = 1003517866915"
                )
            )
        ).one()
        assert creds == ("enc-remid-a", "enc-sid-a", "enc-sess-a", "enc-tok-a"), (
            f"creds mismatch: {creds}"
        )

        # 3. username 已回填
        usernames = sorted(
            row[0]
            for row in (
                await conn.execute(text("SELECT username FROM users ORDER BY username"))
            ).all()
        )
        assert usernames == [
            "persona_1003517866915",
            "persona_1004198901469",
            "persona_1005000000001",
        ], f"unexpected usernames: {usernames}"

        # 4. 旧列已删
        old_cols = (
            await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='users' AND column_name IN "
                    "('persona_id','display_name','avatar_url','encrypted_remid')"
                )
            )
        ).all()
        assert old_cols == [], f"old users columns still present: {old_cols}"

        # 5. server_memberships.user_id 仍指向 admin user
        mem = (
            await conn.execute(
                text(
                    "SELECT u.username FROM server_memberships m "
                    "JOIN users u ON u.id = m.user_id LIMIT 1"
                )
            )
        ).scalar_one()
        assert mem == "persona_1005000000001", f"membership user mismatch: {mem}"

        # 6. partial unique index 真实存在（pg_indexes）
        idx = (
            await conn.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE tablename='ea_bindings' AND indexname='uq_ea_bindings_user_primary'"
                )
            )
        ).scalar_one_or_none()
        assert idx is not None and "is_primary" in idx.lower(), f"partial index missing: {idx}"

        # 7. 0017：remid 时代建的号记 legacy，现有绑定记 verified_via=legacy
        statuses = {row[0] for row in (await conn.execute(text("SELECT status FROM users"))).all()}
        assert statuses == {"legacy"}, f"user status mismatch: {statuses}"
        via = {
            row[0]
            for row in (await conn.execute(text("SELECT verified_via FROM ea_bindings"))).all()
        }
        assert via == {"legacy"}, f"verified_via mismatch: {via}"

        # 8. 0017：persona 唯一约束改为只管未冻结的行
        persona_idx = (
            await conn.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE tablename='ea_bindings' AND indexname='uq_ea_bindings_persona_active'"
                )
            )
        ).scalar_one_or_none()
        assert persona_idx is not None and "is_frozen" in persona_idx.lower(), (
            f"persona partial index missing: {persona_idx}"
        )
        for table in (
            "email_verifications",
            "invite_codes",
            "groups",
            "group_members",
            "group_invites",
            "site_settings",
            "group_ea_accounts",
            "group_servers",
        ):
            reg = (await conn.execute(text(f"SELECT to_regclass('public.{table}')"))).scalar_one()
            assert reg is not None, f"{table} missing"

        # 9. 0019：群组审计记在 audit_logs.group_id 上，带索引
        group_idx = (
            await conn.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE tablename='audit_logs' AND indexname='ix_audit_logs_group_id'"
                )
            )
        ).scalar_one_or_none()
        assert group_idx is not None, "audit_logs.group_id index missing"

        # 10. 0021：审计记 EA 侧实际执行的账号
        executor_col = (
            await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name='audit_logs' AND column_name='executor_persona_id'"
                )
            )
        ).scalar_one_or_none()
        assert executor_col is not None, "audit_logs.executor_persona_id missing"

        # 11. 0022：冻结账号记时间、原因、操作人
        frozen_cols = (
            (
                await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name='users' AND column_name LIKE 'frozen_%'"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert set(frozen_cols) == {"frozen_at", "frozen_reason", "frozen_by"}, frozen_cols

    await engine.dispose()
    print("assert_upgraded: all checks passed")


async def assert_downgraded() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, future=True)

    async with engine.connect() as conn:
        # 1. ea_bindings 表已删
        exists = (await conn.execute(text("SELECT to_regclass('public.ea_bindings')"))).scalar_one()
        assert exists is None, "ea_bindings still exists after downgrade"

        # 2. users 旧列回来
        cols = sorted(
            row[0]
            for row in (
                await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name='users' AND column_name IN "
                        "('persona_id','display_name','encrypted_remid')"
                    )
                )
            ).all()
        )
        assert cols == ["display_name", "encrypted_remid", "persona_id"], (
            f"old users columns not restored: {cols}"
        )

        # 3. persona_id 数据从 primary binding 拷回
        personas = sorted(
            row[0] for row in (await conn.execute(text("SELECT persona_id FROM users"))).all()
        )
        assert personas == [1003517866915, 1004198901469, 1005000000001], (
            f"persona_id not restored: {personas}"
        )

        # 4. encrypted_remid 正确
        remid = (
            await conn.execute(
                text("SELECT encrypted_remid FROM users WHERE persona_id = 1003517866915")
            )
        ).scalar_one()
        assert remid == "enc-remid-a", f"encrypted_remid mismatch: {remid}"

    await engine.dispose()
    print("assert_downgraded: all checks passed")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "upgraded"
    if mode == "downgraded":
        asyncio.run(assert_downgraded())
    else:
        asyncio.run(assert_upgraded())
