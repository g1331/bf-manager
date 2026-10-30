"""群组的并发规则：只在 PostgreSQL 上跑。

SQLite 没有 SELECT … FOR UPDATE，测不出行锁的等待和等待后读到的新状态，所以这里直接连
DATABASE_URL 指的 PG（CI 的 pytest 步骤就是 PG）；本地默认的 in-memory SQLite 下跳过。
用两个独立 session 显式安排交错：A 先拿锁改状态，等 B 确实卡在锁上，A 再提交。
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from app.core.config import get_settings
from app.core.passwords import hash_password
from app.models import Base, EaBinding, Group, GroupInvite, GroupMember, User
from app.services import group_service as gs
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.environ.get("DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL.startswith("postgresql"), reason="行锁只能在 PostgreSQL 上验证"
)


@pytest_asyncio.fixture
async def sessions():
    engine = create_async_engine(DATABASE_URL, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def _user(sm, uid: int) -> int:
    async with sm() as db:
        db.add(
            User(
                id=uid,
                username=f"lock{uid}",
                email=f"lock{uid}@example.com",
                email_verified_at=datetime.now(UTC),
                local_password_hash=hash_password("pw-12345678"),
                role="user",
                status="active",
            )
        )
        await db.flush()
        db.add(
            EaBinding(
                user_id=uid,
                persona_id=900000 + uid,
                display_name=f"L{uid}",
                verified_via="email",
                is_primary=True,
                is_frozen=False,
            )
        )
        await db.commit()
    return uid


async def _wait_until_blocked(sm, timeout: float = 5.0) -> None:
    """等到有别的连接卡在行锁上，确认交错真的发生了"""
    async with sm() as db:
        for _ in range(int(timeout / 0.05)):
            waiting = await db.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE wait_event_type = 'Lock' AND datname = current_database()"
                )
            )
            if waiting:
                return
            await asyncio.sleep(0.05)
    raise AssertionError("另一个事务没有在等锁")


async def test_concurrent_create_group_respects_limit(sessions, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "group_owned_limit_per_user", 1)
    uid = await _user(sessions, 1)

    async def create() -> str:
        async with sessions() as db:
            try:
                await gs.create_group(db, await db.get(User, uid), "并发群")
                return "ok"
            except gs.GroupError as e:
                return e.code

    results = await asyncio.gather(*[create() for _ in range(4)])
    assert sorted(results) == ["GROUP_LIMIT"] * 3 + ["ok"]
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Group)) == 1


async def _invite_id(db: AsyncSession, gid: int, owner: User) -> int:
    invite, _ = await gs.create_invite(db, gid, owner, role="admin", max_uses=1, ttl_hours=24)
    return invite.id


OwnerAction = Callable[[AsyncSession, int, User, int], Awaitable[object]]

ACTIONS: dict[str, OwnerAction] = {
    "rename": lambda db, gid, user, _inv: gs.rename_group(db, gid, user, "改掉"),
    "delete": lambda db, gid, user, _inv: gs.delete_group(db, gid, user),
    "create_invite": lambda db, gid, user, _inv: gs.create_invite(
        db, gid, user, role="admin", max_uses=1, ttl_hours=24
    ),
    "revoke_invite": lambda db, gid, user, inv: gs.revoke_invite(db, gid, inv, user),
}


@pytest.mark.parametrize("action", sorted(ACTIONS))
async def test_owner_demoted_while_waiting_for_lock_is_rejected(sessions, action) -> None:
    """B 是群主，发出操作后卡在群锁上；A 在锁里把 B 降成管理员并提交。B 拿到锁后要按新身份被拒"""
    a = await _user(sessions, 1)
    b = await _user(sessions, 2)
    async with sessions() as db:
        owner_a = await db.get(User, a)
        group = await gs.create_group(db, owner_a, "降级测试")
        gid = group.id
        db.add(GroupMember(group_id=gid, user_id=b, role="owner"))
        await db.commit()
        invite_id = await _invite_id(db, gid, owner_a)

    async with sessions() as db_a:
        await gs._lock_group(db_a, gid)
        await db_a.execute(
            update(GroupMember)
            .where(GroupMember.group_id == gid, GroupMember.user_id == b)
            .values(role="admin")
        )

        async def run_b() -> object:
            async with sessions() as db_b:
                return await ACTIONS[action](db_b, gid, await db_b.get(User, b), invite_id)

        task = asyncio.create_task(run_b())
        await _wait_until_blocked(sessions)
        await db_a.commit()

    with pytest.raises(gs.GroupError) as exc:
        await task
    assert exc.value.code == "GROUP_FORBIDDEN"

    async with sessions() as db:
        group = await db.get(Group, gid)
        assert group is not None and group.name == "降级测试"
        invites = (await db.scalars(select(GroupInvite).where(GroupInvite.group_id == gid))).all()
        assert [(i.id, i.revoked_at) for i in invites] == [(invite_id, None)]
