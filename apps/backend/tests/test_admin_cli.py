"""CLI 子命令单元测试。

策略：直接调用 cmd_* 异步实现函数（_run_create_admin 等），传入测试 session，
绕开 argparse 与 get_sessionmaker 全局单例，避免重置全局 engine。
"""

from __future__ import annotations

from app.core.passwords import verify_password
from app.models import EaBinding, User
from app.services.user_service import UserService
from sqlalchemy import select


async def test_create_local_admin_then_grant(test_session) -> None:
    users = UserService(test_session)

    admin = await users.create_local_admin(
        username="root", password="s3cret-pw", email="root@example.com"
    )
    assert admin.username == "root"
    assert admin.role == "admin"
    assert admin.local_password_hash is not None
    assert verify_password("s3cret-pw", admin.local_password_hash)


async def test_create_admin_rejects_duplicate(test_session) -> None:
    users = UserService(test_session)
    await users.create_local_admin(username="root", password="pw")
    try:
        await users.create_local_admin(username="root", password="pw2")
    except ValueError as e:
        assert "已存在" in str(e)
    else:
        raise AssertionError("expected ValueError on duplicate username")


async def test_reset_password(test_session) -> None:
    users = UserService(test_session)
    admin = await users.create_local_admin(username="root", password="old")

    await users.set_local_password(admin, "brand-new-pw")
    refreshed = await users.get_by_username("root")
    assert refreshed is not None
    assert verify_password("brand-new-pw", refreshed.local_password_hash)
    assert not verify_password("old", refreshed.local_password_hash)


async def test_verify_local_password_returns_none_for_no_password(test_session) -> None:
    """EA cookie 自动创建的 user (local_password_hash IS NULL) 不能走 local-login"""
    user = User(
        username="persona_999",
        local_password_hash=None,
        role="user",
        is_active=True,
        is_frozen=False,
    )
    test_session.add(user)
    await test_session.commit()

    users = UserService(test_session)
    assert await users.verify_local_password("persona_999", "anything") is None


async def test_grant_admin_requires_existing_user(test_session) -> None:
    users = UserService(test_session)
    try:
        await users.grant_admin(99999999)
    except ValueError as e:
        assert "不存在" in str(e)
    else:
        raise AssertionError("expected ValueError when persona has no user")


async def test_grant_admin_promotes_existing_user(test_session) -> None:
    """grant-admin 用 binding 反查 user 后写 role=admin"""
    user = User(username="persona_42", role="user", is_active=True, is_frozen=False)
    test_session.add(user)
    await test_session.flush()
    test_session.add(
        EaBinding(
            user_id=user.id,
            persona_id=42,
            display_name="X",
            is_primary=True,
            is_frozen=False,
        )
    )
    await test_session.commit()

    users = UserService(test_session)
    promoted = await users.grant_admin(42)
    assert promoted.role == "admin"
    assert promoted.username == "persona_42"


async def test_revoke_admin_demotes(test_session) -> None:
    user = User(username="persona_42", role="admin", is_active=True, is_frozen=False)
    test_session.add(user)
    await test_session.flush()
    test_session.add(EaBinding(user_id=user.id, persona_id=42, is_primary=True, is_frozen=False))
    await test_session.commit()

    users = UserService(test_session)
    demoted = await users.revoke_admin(42)
    assert demoted.role == "user"


async def test_list_admins_query(test_session) -> None:
    """list-admins 等价的 query：role='admin' filter"""
    users = UserService(test_session)
    await users.create_local_admin(username="a1", password="pw")
    await users.create_local_admin(username="a2", password="pw")
    # 普通 user 不应入选
    test_session.add(User(username="bystander", role="user", is_active=True, is_frozen=False))
    await test_session.commit()

    rows = (await test_session.scalars(select(User).where(User.role == "admin"))).all()
    usernames = sorted(u.username for u in rows)
    assert usernames == ["a1", "a2"]
