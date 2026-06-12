"""get_bf1_client_for_binding 工厂：凭据解密与刷新回写目标

binding 工厂与池工厂的关键差异是 on_session_refreshed 回调必须按 binding.id 回写
EaBindingService——若错用 EAAccountService，刷新出的新 sid 会因 pid 不在池中被静默
丢弃（gateway_factory 文件头注释记录的陷阱）。本用例锁定回写目标与解密入参。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar

import pytest
from app.core.security import get_cipher
from app.models import EaBinding, User
from app.services.bf1 import gateway_factory
from app.services.bf1.gateway_factory import get_bf1_client_for_binding

PERSONA_ID = 1003517866915


class _FakeGatewayClient:
    """捕获构造参数与回调的假 client，对齐 BF1GatewayClient 构造签名"""

    instances: ClassVar[list[_FakeGatewayClient]] = []

    def __init__(self, *, pid, remid=None, sid=None, session=None, on_session_refreshed=None):
        self.pid = pid
        self.remid = remid
        self.sid = sid
        self.session = session
        self.on_session_refreshed = on_session_refreshed
        self.access_token = None
        self.login_calls: list[tuple[str, str]] = []
        self.http_session = None
        _FakeGatewayClient.instances.append(self)

    async def login(self, remid: str, sid: str):
        self.login_calls.append((remid, sid))
        self.access_token = "fake-token"
        return "fake-token"


@pytest.fixture(autouse=True)
def _reset_fake_instances():
    _FakeGatewayClient.instances = []
    yield
    _FakeGatewayClient.instances = []


async def _make_binding(test_session, *, with_session: bool = True) -> EaBinding:
    cipher = get_cipher()
    user = User(
        id=1,
        username=f"persona_{PERSONA_ID}",
        local_password_hash=None,
        email=None,
        role="user",
        is_active=True,
        is_frozen=False,
        last_login_at=datetime.now(UTC),
    )
    test_session.add(user)
    await test_session.flush()
    binding = EaBinding(
        user_id=user.id,
        persona_id=PERSONA_ID,
        display_name="TestUser",
        avatar_url=None,
        encrypted_remid=cipher.encrypt("remid-plain"),
        encrypted_sid=cipher.encrypt("sid-plain"),
        encrypted_session=cipher.encrypt("session-plain") if with_session else None,
        encrypted_access_token=None,
        is_primary=True,
        is_frozen=False,
        last_verified_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    test_session.add(binding)
    await test_session.commit()
    return binding


async def test_factory_decrypts_credentials_and_logs_in(test_session, monkeypatch):
    monkeypatch.setattr(gateway_factory, "BF1GatewayClient", _FakeGatewayClient)
    binding = await _make_binding(test_session)

    async with get_bf1_client_for_binding(test_session, binding) as client:
        assert client.pid == PERSONA_ID
        assert client.remid == "remid-plain"
        assert client.sid == "sid-plain"
        assert client.session == "session-plain"
        # 与池工厂相同的预热语义：access_token 为空时进入前已 login 过一次
        assert client.login_calls == [("remid-plain", "sid-plain")]


async def test_refresh_callback_writes_back_to_binding(test_session, monkeypatch):
    """回调触发后新 sid/session 必须落到 ea_bindings 行（而非账号池）"""
    monkeypatch.setattr(gateway_factory, "BF1GatewayClient", _FakeGatewayClient)
    binding = await _make_binding(test_session)
    old_verified_at = binding.last_verified_at

    async with get_bf1_client_for_binding(test_session, binding) as client:
        # 模拟 gateway 在凭据刷新后触发回调（回调签名携带 pid，但回写按 binding.id 寻址）
        await client.on_session_refreshed(PERSONA_ID, "new-sid", "new-session")

    await test_session.refresh(binding)
    cipher = get_cipher()
    assert cipher.decrypt(binding.encrypted_sid) == "new-sid"
    assert cipher.decrypt(binding.encrypted_session) == "new-session"
    assert binding.last_verified_at is not None
    assert binding.last_verified_at.replace(tzinfo=UTC) > old_verified_at


async def test_factory_rejects_binding_without_credentials(test_session, monkeypatch):
    monkeypatch.setattr(gateway_factory, "BF1GatewayClient", _FakeGatewayClient)
    binding = await _make_binding(test_session)
    binding.encrypted_remid = None
    await test_session.commit()

    with pytest.raises(ValueError, match="凭据不完整"):
        async with get_bf1_client_for_binding(test_session, binding):
            pass  # pragma: no cover

    assert _FakeGatewayClient.instances == []
