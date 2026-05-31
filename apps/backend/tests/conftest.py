"""测试通用 fixture

策略：
- 默认走 in-memory sqlite，不依赖 postgres / redis；CI 若已显式 set DATABASE_URL
  会按 CI 配置走，setdefault 不覆盖
- fixture 提供独立 in-memory engine + schema，每用例隔离
- 通过 dependency_overrides 把 `get_db` 与 `get_current_user` 换成测试版本，
  避免在测试里发起任何 EA Gateway 真实请求
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

# 在 import app 之前先把测试用的密钥与 DB URL 注入环境
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("EA_CRED_ENCRYPTION_KEY", "ZGV2LW9ubHktY2hhbmdlLW1lLWluLXByb2QtMzJieXQ=")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-not-secure-but-deterministic")
os.environ.setdefault("ENVIRONMENT", "test")

import pytest_asyncio
from app.api.deps import get_current_user, get_current_user_optional
from app.db.session import get_db
from app.main import create_app
from app.models import Base, EaBinding, User
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload


async def _reload_with_bindings(session, user_id: int) -> User:
    """Eager-load ea_bindings 模拟真实 get_current_user 的依赖注入行为，
    避免 sqlite async + lazy load 在 fixture-injected user 上抛 MissingGreenlet"""
    user = await session.scalar(
        select(User).options(selectinload(User.ea_bindings)).where(User.id == user_id)
    )
    assert user is not None
    return user


def _make_user(*, user_id: int = 1, username: str = "test_user", role: str = "user") -> User:
    return User(
        id=user_id,
        username=username,
        local_password_hash=None,
        email=None,
        role=role,
        is_active=True,
        is_frozen=False,
        last_login_at=datetime.now(UTC),
    )


def _make_binding(
    *,
    user_id: int,
    persona_id: int,
    display_name: str | None = None,
    is_primary: bool = True,
) -> EaBinding:
    return EaBinding(
        user_id=user_id,
        persona_id=persona_id,
        display_name=display_name or f"TestPersona_{persona_id}",
        avatar_url=None,
        encrypted_remid=None,
        encrypted_sid=None,
        encrypted_session=None,
        encrypted_access_token=None,
        is_primary=is_primary,
        is_frozen=False,
        last_verified_at=datetime.now(UTC),
    )


@pytest_asyncio.fixture
async def test_session():
    """每个用例独立 sqlite 引擎 + schema"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def client(test_session):
    """裸客户端（未登录态）"""
    app = create_app()

    async def _override_get_db():
        yield test_session

    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def user_client(test_session):
    """普通用户登录态客户端，返回 (client, user)。

    user 自带一条 primary binding（persona_id=1003517866915），覆盖「EA 登录用户」常态。
    """
    user = _make_user(user_id=1, username="persona_1003517866915", role="user")
    test_session.add(user)
    await test_session.flush()
    test_session.add(
        _make_binding(user_id=user.id, persona_id=1003517866915, display_name="TestUser")
    )
    await test_session.commit()
    user = await _reload_with_bindings(test_session, user.id)

    app = create_app()

    async def _override_get_db():
        yield test_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac, user
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_client(test_session):
    """平台 admin 登录态客户端，返回 (client, admin)。

    admin 自带一条 primary binding（persona_id=1004198901469），覆盖「EA 登录的 admin」常态。
    """
    admin = _make_user(user_id=99, username="persona_1004198901469", role="admin")
    test_session.add(admin)
    await test_session.flush()
    test_session.add(
        _make_binding(user_id=admin.id, persona_id=1004198901469, display_name="AdminUser")
    )
    await test_session.commit()
    admin = await _reload_with_bindings(test_session, admin.id)

    app = create_app()

    async def _override_get_db():
        yield test_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_current_user_optional] = lambda: admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac, admin
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def local_admin_client(test_session):
    """CLI 创建的本地 admin 登录态客户端（无任何 ea_binding），返回 (client, admin)"""
    from app.core.passwords import hash_password

    admin = User(
        id=100,
        username="root",
        local_password_hash=hash_password("test-pw"),
        email=None,
        role="admin",
        is_active=True,
        is_frozen=False,
        last_login_at=datetime.now(UTC),
    )
    test_session.add(admin)
    await test_session.commit()
    admin = await _reload_with_bindings(test_session, admin.id)

    app = create_app()

    async def _override_get_db():
        yield test_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_current_user_optional] = lambda: admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac, admin
    app.dependency_overrides.clear()
