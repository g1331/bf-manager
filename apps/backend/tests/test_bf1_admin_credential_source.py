"""服管审计 payload 的 credential_source 标注

provider 经实例属性回传本次实际使用的凭据来源（"binding" / "pool"），service 软读取
写进审计 payload。锁定三件事：有属性则成功/失败审计都带、无属性的旧 provider 不带
（Protocol 兼容）、acquire 进入后才标注。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from app.api.errors import EAApiError
from app.models import AuditLog
from app.services.bf1.server_admin_service import BF1ServerAdminService
from sqlalchemy import select

GAME_ID = 10970335350265
RSP_DETAIL = {"rspInfo": {"server": {"serverId": "12478776"}}}


class _FakeClient:
    def __init__(self, *, fail_member_op: bool = False) -> None:
        self._fail = fail_member_op

    async def getFullServerDetails(self, gameId):  # noqa: N802, N803 (对齐 gateway 签名)
        return {"result": RSP_DETAIL}

    async def addServerVip(self, personaId, serverId):  # noqa: N802, N803
        if self._fail:
            return "ServerNotRestartableException"
        return {"ok": True}


class _FakeProvider:
    """无 credential_source 属性的旧式 provider（兼容性锁定用）"""

    def __init__(self, client: _FakeClient) -> None:
        self._client = client

    @asynccontextmanager
    async def acquire(self):
        yield self._client


class _FakeProviderWithSource(_FakeProvider):
    credential_source = "binding"


async def _latest_audit(test_session) -> AuditLog:
    row = await test_session.scalar(select(AuditLog).order_by(AuditLog.id.desc()).limit(1))
    assert row is not None
    return row


def _service(test_session, user, provider) -> BF1ServerAdminService:
    return BF1ServerAdminService(test_session, user=user, game_id=GAME_ID, client_provider=provider)


async def test_success_audit_carries_credential_source(admin_client, test_session):
    _, admin = admin_client
    service = _service(test_session, admin, _FakeProviderWithSource(_FakeClient()))

    await service.add_vip(999)

    audit = await _latest_audit(test_session)
    assert audit.result == "success"
    assert audit.payload["credential_source"] == "binding"


async def test_failure_audit_carries_credential_source(admin_client, test_session):
    _, admin = admin_client
    service = _service(
        test_session, admin, _FakeProviderWithSource(_FakeClient(fail_member_op=True))
    )

    with pytest.raises(EAApiError):
        await service.add_vip(999)

    audit = await _latest_audit(test_session)
    assert audit.result == "failure"
    assert audit.payload["credential_source"] == "binding"


async def test_provider_without_source_attribute_leaves_payload_untouched(
    admin_client, test_session
):
    """旧 provider / 测试 fake 无该属性：payload 不带键，Protocol 兼容不被破坏"""
    _, admin = admin_client
    service = _service(test_session, admin, _FakeProvider(_FakeClient()))

    await service.add_vip(999)

    audit = await _latest_audit(test_session)
    assert audit.result == "success"
    assert "credential_source" not in audit.payload
