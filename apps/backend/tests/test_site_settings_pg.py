"""站点设置的并发写：只在 PostgreSQL 上跑，原因见 test_group_locks_pg.py"""

from __future__ import annotations

import asyncio
from itertools import pairwise

from app.models import AuditLog, User
from app.services import site_settings_service as ss
from sqlalchemy import select

from tests.test_group_locks_pg import _user, pytestmark, sessions  # noqa: F401


async def test_concurrent_first_set_and_audit_chain(sessions) -> None:  # noqa: F811
    """库里还没有设置时几个管理员同时切换：都要成功，审计的 from 要接上前一条的 to"""
    uids = [await _user(sessions, i) for i in range(1, 5)]
    modes = ["open", "closed", "invite", "open"]

    async def switch(uid: int, mode: str) -> None:
        async with sessions() as db:
            await ss.set_registration_mode(db, mode, await db.get(User, uid))

    await asyncio.gather(*[switch(u, m) for u, m in zip(uids, modes, strict=True)])

    async with sessions() as db:
        logs = (
            await db.scalars(
                select(AuditLog)
                .where(AuditLog.action == "site_registration_mode")
                .order_by(AuditLog.id)
            )
        ).all()
        assert len(logs) == 4
        assert logs[0].payload["from"] == ss.default_registration_mode()
        for prev, cur in pairwise(logs):
            assert cur.payload["from"] == prev.payload["to"]
        assert await ss.get_registration_mode(db) == logs[-1].payload["to"]
