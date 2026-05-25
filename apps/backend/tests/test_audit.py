"""审计日志路由：未登录 401 + 普通用户只看自己 + admin 看全部"""

from __future__ import annotations

from app.models import AuditLog
from app.services.audit_service import AuditService


async def test_audit_logs_requires_login(client) -> None:
    resp = await client.get("/api/v1/audit-logs")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


async def test_audit_logs_user_only_sees_own(user_client, test_session) -> None:
    ac, user = user_client
    # 用 service 写两条日志：一条自己的，一条别人的
    svc = AuditService(test_session)
    await svc.record(
        user_id=user.id,
        acting_persona_id=1003517866915,  # 来自 user_client fixture 注入的 binding
        action="kick_player",
        game="bf1",
        server_id=12345,
        target_persona_id=999,
        payload={},
        result="success",
    )

    other = AuditLog(
        user_id=999,
        acting_persona_id=88888,
        game="bf1",
        server_id=54321,
        action="add_ban",
        target_persona_id=777,
        payload={},
        result="success",
    )
    test_session.add(other)
    await test_session.commit()

    resp = await ac.get("/api/v1/audit-logs")
    assert resp.status_code == 200
    items = resp.json()["items"]
    # 普通用户只能看到自己的一条
    assert len(items) == 1
    assert items[0]["user_id"] == user.id
    assert items[0]["action"] == "kick_player"


async def test_audit_logs_admin_sees_all(admin_client, test_session) -> None:
    ac, admin = admin_client
    svc = AuditService(test_session)
    await svc.record(
        user_id=admin.id,
        acting_persona_id=1004198901469,  # 来自 admin_client fixture 注入的 binding
        action="kick_player",
        game="bf1",
        server_id=1,
        target_persona_id=1,
        payload={},
        result="success",
    )

    other = AuditLog(
        user_id=12,
        acting_persona_id=42,
        game="bfv",
        server_id=2,
        action="add_ban",
        target_persona_id=2,
        payload={},
        result="failure",
    )
    test_session.add(other)
    await test_session.commit()

    resp = await ac.get("/api/v1/audit-logs")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2

    # 过滤：game=bfv 只剩一条
    resp = await ac.get("/api/v1/audit-logs?game=bfv")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["game"] == "bfv"
