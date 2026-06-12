"""BindingFirstBF1ClientProvider 的凭据选择与降级逻辑

服管操作凭据选择顺序：发起者 primary binding（且为该服 RSP 管理员）→ 后台账号池。
本用例 monkeypatch client_provider 命名空间里的两个工厂，用 sink 记录实际进入了
哪条链路，锁定全部降级条件与「执行阶段绝不换凭据重试」不变量。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from app.api.errors import EAApiError
from app.domain.games.bf1 import client_provider as cp_module
from app.domain.games.bf1.client_provider import BindingFirstBF1ClientProvider
from app.models import EaBinding
from sqlalchemy import select

GAME_ID = 10970335350265
RSP_DETAIL = {"result": {"rspInfo": {"server": {"serverId": "12478776"}}}}


class _FakeBindingClient:
    def __init__(self, *, access_token: str | None, detail) -> None:
        self.access_token = access_token
        self._detail = detail
        self.probe_called = False

    async def getFullServerDetails(self, gameId):  # noqa: N802, N803 (对齐 gateway 签名)
        self.probe_called = True
        if isinstance(self._detail, Exception):
            raise self._detail
        return self._detail


def _patch_factories(
    monkeypatch,
    sink: dict,
    *,
    binding_client: _FakeBindingClient | None = None,
):
    """替换两个工厂：binding 工厂 yield 指定 fake client，池工厂 yield 占位 client"""

    @asynccontextmanager
    async def fake_binding_factory(db, binding: EaBinding):
        sink["binding_factory_binding_id"] = binding.id
        assert binding_client is not None, "binding 工厂不应被进入"
        try:
            yield binding_client
        finally:
            sink["binding_factory_exited"] = True

    @asynccontextmanager
    async def fake_pool_factory(db):
        sink["pool_factory_entered"] = True
        yield object()

    monkeypatch.setattr(cp_module, "get_bf1_client_for_binding", fake_binding_factory)
    monkeypatch.setattr(cp_module, "get_bf1_client", fake_pool_factory)


async def _get_binding(test_session, user_id: int) -> EaBinding:
    binding = await test_session.scalar(select(EaBinding).where(EaBinding.user_id == user_id))
    assert binding is not None
    return binding


async def _make_binding_usable(test_session, user_id: int) -> EaBinding:
    """conftest 的 binding 凭据全 NULL，补上非空密文模拟「EA 登录用户」常态"""
    binding = await _get_binding(test_session, user_id)
    binding.encrypted_remid = "encrypted-remid"
    binding.encrypted_sid = "encrypted-sid"
    await test_session.commit()
    return binding


async def test_no_binding_falls_back_to_pool(local_admin_client, test_session, monkeypatch):
    """本地 admin 无任何 binding：直接走池，binding 工厂不被触达"""
    _, admin = local_admin_client
    sink: dict = {}
    _patch_factories(monkeypatch, sink)

    provider = BindingFirstBF1ClientProvider(test_session, user=admin, game_id=GAME_ID)
    async with provider.acquire():
        pass

    assert sink.get("pool_factory_entered") is True
    assert "binding_factory_binding_id" not in sink
    assert provider.credential_source == "pool"


async def test_binding_without_credentials_falls_back_to_pool(
    user_client, test_session, monkeypatch
):
    """binding 存在但凭据为 NULL（解绑后形态 / conftest 默认形态）：走池"""
    _, user = user_client
    sink: dict = {}
    _patch_factories(monkeypatch, sink)

    provider = BindingFirstBF1ClientProvider(test_session, user=user, game_id=GAME_ID)
    async with provider.acquire():
        pass

    assert sink.get("pool_factory_entered") is True
    assert "binding_factory_binding_id" not in sink
    assert provider.credential_source == "pool"


async def test_frozen_binding_falls_back_to_pool(user_client, test_session, monkeypatch):
    _, user = user_client
    binding = await _make_binding_usable(test_session, user.id)
    binding.is_frozen = True
    await test_session.commit()
    sink: dict = {}
    _patch_factories(monkeypatch, sink)

    provider = BindingFirstBF1ClientProvider(test_session, user=user, game_id=GAME_ID)
    async with provider.acquire():
        pass

    assert sink.get("pool_factory_entered") is True
    assert "binding_factory_binding_id" not in sink


async def test_non_primary_binding_falls_back_to_pool(user_client, test_session, monkeypatch):
    _, user = user_client
    binding = await _make_binding_usable(test_session, user.id)
    binding.is_primary = False
    await test_session.commit()
    sink: dict = {}
    _patch_factories(monkeypatch, sink)

    provider = BindingFirstBF1ClientProvider(test_session, user=user, game_id=GAME_ID)
    async with provider.acquire():
        pass

    assert sink.get("pool_factory_entered") is True
    assert "binding_factory_binding_id" not in sink


async def test_usable_binding_with_rsp_access_uses_binding(user_client, test_session, monkeypatch):
    """binding 可用 + 登录成功 + 是该服 RSP 管理员：用 binding client，池不被触达"""
    _, user = user_client
    binding = await _make_binding_usable(test_session, user.id)
    fake_client = _FakeBindingClient(access_token="token", detail=RSP_DETAIL)
    sink: dict = {}
    _patch_factories(monkeypatch, sink, binding_client=fake_client)

    provider = BindingFirstBF1ClientProvider(test_session, user=user, game_id=GAME_ID)
    async with provider.acquire() as client:
        assert client is fake_client

    assert sink["binding_factory_binding_id"] == binding.id
    assert sink.get("binding_factory_exited") is True
    assert "pool_factory_entered" not in sink
    assert provider.credential_source == "binding"


async def test_probe_without_rsp_info_falls_back_to_pool(user_client, test_session, monkeypatch):
    """详情可见但无 rspInfo（serverInfo.serverId 非管理员也可见，不能作为权限证据）：走池"""
    _, user = user_client
    await _make_binding_usable(test_session, user.id)
    fake_client = _FakeBindingClient(
        access_token="token",
        detail={"result": {"serverInfo": {"serverId": "12478776"}}},
    )
    sink: dict = {}
    _patch_factories(monkeypatch, sink, binding_client=fake_client)

    provider = BindingFirstBF1ClientProvider(test_session, user=user, game_id=GAME_ID)
    async with provider.acquire():
        pass

    assert fake_client.probe_called is True
    assert sink.get("binding_factory_exited") is True
    assert sink.get("pool_factory_entered") is True
    assert provider.credential_source == "pool"


@pytest.mark.parametrize(
    "detail",
    [RuntimeError("EA 5xx"), "ServerNotRestartableException", {"result": None}],
    ids=["probe-raises", "probe-returns-str", "probe-result-none"],
)
async def test_probe_failure_falls_back_to_pool(user_client, test_session, monkeypatch, detail):
    _, user = user_client
    await _make_binding_usable(test_session, user.id)
    fake_client = _FakeBindingClient(access_token="token", detail=detail)
    sink: dict = {}
    _patch_factories(monkeypatch, sink, binding_client=fake_client)

    provider = BindingFirstBF1ClientProvider(test_session, user=user, game_id=GAME_ID)
    async with provider.acquire():
        pass

    assert sink.get("binding_factory_exited") is True
    assert sink.get("pool_factory_entered") is True
    assert provider.credential_source == "pool"


async def test_login_failure_falls_back_without_probe(user_client, test_session, monkeypatch):
    """login() 失败不抛异常只留 access_token 为空：降级走池，且不发起探测调用"""
    _, user = user_client
    await _make_binding_usable(test_session, user.id)
    fake_client = _FakeBindingClient(access_token=None, detail=RSP_DETAIL)
    sink: dict = {}
    _patch_factories(monkeypatch, sink, binding_client=fake_client)

    provider = BindingFirstBF1ClientProvider(test_session, user=user, game_id=GAME_ID)
    async with provider.acquire():
        pass

    assert fake_client.probe_called is False
    assert sink.get("binding_factory_exited") is True
    assert sink.get("pool_factory_entered") is True
    assert provider.credential_source == "pool"


async def test_binding_factory_error_falls_back_to_pool(user_client, test_session, monkeypatch):
    """工厂进入阶段抛异常（解密失败 / 网络异常）：降级走池"""
    _, user = user_client
    await _make_binding_usable(test_session, user.id)
    sink: dict = {}

    @asynccontextmanager
    async def broken_binding_factory(db, binding):
        raise ValueError("decrypt failed")
        yield  # pragma: no cover

    @asynccontextmanager
    async def fake_pool_factory(db):
        sink["pool_factory_entered"] = True
        yield object()

    monkeypatch.setattr(cp_module, "get_bf1_client_for_binding", broken_binding_factory)
    monkeypatch.setattr(cp_module, "get_bf1_client", fake_pool_factory)

    provider = BindingFirstBF1ClientProvider(test_session, user=user, game_id=GAME_ID)
    async with provider.acquire():
        pass

    assert sink.get("pool_factory_entered") is True
    assert provider.credential_source == "pool"


async def test_no_retry_with_pool_after_binding_handed_over(user_client, test_session, monkeypatch):
    """不变量回归锁：binding 命中交付后，操作阶段异常必须原样穿透，绝不降级池重试。

    kick / ban 等操作非幂等，超时类错误无法区分是否已生效，二次执行有双重处置风险。
    """
    _, user = user_client
    await _make_binding_usable(test_session, user.id)
    fake_client = _FakeBindingClient(access_token="token", detail=RSP_DETAIL)
    sink: dict = {}
    _patch_factories(monkeypatch, sink, binding_client=fake_client)

    provider = BindingFirstBF1ClientProvider(test_session, user=user, game_id=GAME_ID)
    with pytest.raises(EAApiError):
        async with provider.acquire():
            raise EAApiError(code="EA_KICK_FAILED", message="操作超时")

    assert "pool_factory_entered" not in sink
    assert sink.get("binding_factory_exited") is True
    assert provider.credential_source == "binding"
