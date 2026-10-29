"""号池保护：查询失败的分类计数、达阈值先验证再停用、公共查询限流与全站 EA 预算。"""

from __future__ import annotations

from typing import Any

import pytest
from app.api import rate_limit as rate_limit_module
from app.api.errors import EAApiError, EABusyError, NotFoundError
from app.core import ea_budget
from app.core.config import get_settings
from app.core.security import create_access_token, get_cipher
from app.main import create_app
from app.models import EAAccount
from app.services import ea_account_service
from app.services.bf1 import gateway_factory
from app.services.ea_account_service import FAILURE_DISABLE_THRESHOLD, EAAccountService
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

# ===== 假 Redis：覆盖限流与预算用到的命令 =====


class _FakePipeline:
    def __init__(self, redis: _FakeRedis) -> None:
        self._redis = redis
        self._ops: list[tuple[str, tuple[Any, ...]]] = []

    async def __aenter__(self) -> _FakePipeline:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def incr(self, key: str) -> _FakePipeline:
        self._ops.append(("incr", (key,)))
        return self

    def expire(self, key: str, seconds: int) -> _FakePipeline:
        self._ops.append(("expire", (key, seconds)))
        return self

    async def execute(self) -> list[Any]:
        return [await getattr(self._redis, op)(*args) for op, args in self._ops]


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    async def expire(self, key: str, seconds: int) -> bool:
        return True

    def pipeline(self, transaction: bool = True) -> _FakePipeline:
        return _FakePipeline(self)


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    store = _FakeRedis()

    async def _get() -> _FakeRedis:
        return store

    monkeypatch.setattr(rate_limit_module, "get_redis", _get)
    monkeypatch.setattr(ea_budget, "get_redis", _get)
    return store


@pytest.fixture
def small_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_lookup_per_minute", 3)
    monkeypatch.setattr(settings, "rate_limit_lookup_per_day", 100)
    monkeypatch.setattr(settings, "rate_limit_user_multiplier", 2)
    monkeypatch.setattr(settings, "ea_public_budget_per_minute", 2)


def _app_with_probe() -> Any:
    """挂一个带 lookup 限流的探针路由，返回请求里看到的 EA 优先级。"""
    app = create_app()
    router = APIRouter()

    @router.get("/probe", dependencies=[rate_limit_module.rate_limit("lookup")])
    async def _probe() -> dict[str, bool]:
        return {"public": ea_budget.is_public()}

    app.include_router(router, prefix="/test")
    return app


async def _hit(app: Any, ip: str, n: int, cookies: dict[str, str] | None = None) -> list[int]:
    transport = ASGITransport(app=app, client=(ip, 12345))
    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies) as c:
        return [(await c.get("/test/probe")).status_code for _ in range(n)]


# ===== 限流 =====


async def test_anonymous_ip_is_limited_per_minute(fake_redis, small_limits) -> None:
    app = _app_with_probe()
    assert await _hit(app, "8.8.8.8", 4) == [200, 200, 200, 429]
    # 另一个 IP 不受影响
    assert await _hit(app, "8.8.4.4", 1) == [200]

    transport = ASGITransport(app=app, client=("8.8.8.8", 1))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/test/probe")
    body = resp.json()["error"]
    assert body["code"] == "TOO_MANY_REQUESTS"
    assert body["message"].startswith("本站为公益项目，查询账号有限，请 ")
    assert 1 <= int(resp.headers["retry-after"]) <= 60
    assert any(k.startswith("bfm:rl:blocked:") for k in fake_redis.store)


async def test_ipv6_counts_by_64_prefix(fake_redis, small_limits) -> None:
    app = _app_with_probe()
    assert await _hit(app, "2400:d320:2353:300::1", 3) == [200, 200, 200]
    # 同一 /64 下换个地址不能绕过
    assert await _hit(app, "2400:d320:2353:300::abcd", 1) == [429]
    assert await _hit(app, "2400:d320:2353:301::1", 1) == [200]


async def test_logged_in_user_gets_multiplied_quota(fake_redis, small_limits) -> None:
    app = _app_with_probe()
    token = create_access_token(subject=42)
    cookies = {"bfm_access_token": token}
    assert await _hit(app, "8.8.8.8", 7, cookies) == [200] * 6 + [429]
    # 账号计数和该 IP 的匿名计数互不影响
    assert await _hit(app, "8.8.8.8", 1) == [200]


async def test_private_and_loopback_are_not_limited(fake_redis, small_limits) -> None:
    app = _app_with_probe()
    assert await _hit(app, "127.0.0.1", 5) == [200] * 5
    assert await _hit(app, "172.18.0.5", 5) == [200] * 5
    # 内部请求也不计入公共 EA 预算
    transport = ASGITransport(app=app, client=("127.0.0.1", 1))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        assert (await c.get("/test/probe")).json() == {"public": False}


async def test_read_bucket_counts_separately(fake_redis, small_limits, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "rate_limit_read_per_minute", 2)
    app = _app_with_probe()
    router = APIRouter()

    @router.get("/read", dependencies=[rate_limit_module.rate_limit("read")])
    async def _read() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(router, prefix="/test")
    transport = ASGITransport(app=app, client=("8.8.8.8", 1))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        assert [(await c.get("/test/read")).status_code for _ in range(3)] == [200, 200, 429]
        # 只读额度用完不影响查询额度
        assert (await c.get("/test/probe")).status_code == 200


async def test_redis_failure_lets_requests_through(monkeypatch, small_limits) -> None:
    async def _broken() -> Any:
        raise ConnectionError("redis down")

    monkeypatch.setattr(rate_limit_module, "get_redis", _broken)
    assert await _hit(_app_with_probe(), "8.8.8.8", 5) == [200] * 5


async def test_rate_limited_route_marks_request_public(fake_redis) -> None:
    transport = ASGITransport(app=_app_with_probe(), client=("8.8.8.8", 1))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/test/probe")
    assert resp.json() == {"public": True}


# ===== 全站 EA 预算 =====


async def test_budget_ignores_system_requests(fake_redis, small_limits) -> None:
    for _ in range(5):
        await ea_budget.acquire()
    assert fake_redis.store == {}


async def test_budget_rejects_public_requests_over_limit(fake_redis, small_limits) -> None:
    # 每个测试跑在独立的任务里，这里标记 public 不会带到其他测试
    ea_budget.mark_public()
    await ea_budget.acquire()
    await ea_budget.acquire()
    with pytest.raises(EABusyError) as exc_info:
        await ea_budget.acquire()
    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "EA_BUSY"
    assert 1 <= int(exc_info.value.headers["Retry-After"]) <= 60


# ===== 失败分类与停用前验证 =====


async def _seed_account(session, *, failure_count: int = 0) -> EAAccount:
    cipher = get_cipher()
    account = EAAccount(
        persona_id=2001,
        display_name="pool",
        encrypted_remid=cipher.encrypt("remid-value"),
        encrypted_sid=cipher.encrypt("sid-value"),
        encrypted_session=None,
        encrypted_access_token=None,
        enabled=True,
        failure_count=failure_count,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account


async def _reload(session, account_id: int) -> EAAccount:
    session.expire_all()
    account = await session.scalar(select(EAAccount).where(EAAccount.id == account_id))
    assert account is not None
    return account


class _LoggedInClient:
    def __init__(self, **kwargs: Any) -> None:
        # 有 access_token 时工厂不再登录；check_login=False 让工厂不把登录态写进进程缓存
        self.access_token = "token"
        self.check_login = False
        self.http_session = None

    async def login(self, remid: str, sid: str) -> str:
        return "token"


@pytest.fixture
def fake_pool_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gateway_factory, "BF1GatewayClient", _LoggedInClient)


async def test_not_found_inside_pool_client_counts_as_success(
    test_session, fake_pool_client
) -> None:
    account = await _seed_account(test_session, failure_count=FAILURE_DISABLE_THRESHOLD - 1)
    with pytest.raises(NotFoundError):
        async with gateway_factory.get_bf1_client(test_session):
            raise NotFoundError(resource="persona 1")
    refreshed = await _reload(test_session, account.id)
    assert refreshed.failure_count == 0
    assert refreshed.enabled is True


async def test_upstream_error_inside_pool_client_counts_as_failure(
    test_session, fake_pool_client
) -> None:
    account = await _seed_account(test_session)
    with pytest.raises(EAApiError):
        async with gateway_factory.get_bf1_client(test_session):
            raise EAApiError(code="EA_X", message="upstream")
    refreshed = await _reload(test_session, account.id)
    assert refreshed.failure_count == 1


async def test_threshold_with_passing_verify_keeps_account(test_session, monkeypatch) -> None:
    account = await _seed_account(test_session, failure_count=FAILURE_DISABLE_THRESHOLD - 1)

    async def _verify_ok(self: EAAccountService, account_id: int) -> Any:
        await self.mark_used(account.persona_id)
        return type("R", (), {"success": True})()

    monkeypatch.setattr(EAAccountService, "verify", _verify_ok)
    await EAAccountService(test_session).mark_failure(account.persona_id)
    refreshed = await _reload(test_session, account.id)
    assert refreshed.enabled is True
    assert refreshed.failure_count == 0


async def test_threshold_with_failing_verify_disables_account(test_session, monkeypatch) -> None:
    account = await _seed_account(test_session, failure_count=FAILURE_DISABLE_THRESHOLD - 1)

    async def _verify_fail(self: EAAccountService, account_id: int) -> Any:
        await self.mark_failure(account.persona_id, verify_before_disable=False)
        return type("R", (), {"success": False})()

    monkeypatch.setattr(EAAccountService, "verify", _verify_fail)
    await EAAccountService(test_session).mark_failure(account.persona_id)
    refreshed = await _reload(test_session, account.id)
    assert refreshed.enabled is False
    assert not ea_account_service._verifying


async def test_threshold_with_verify_error_keeps_account(test_session, monkeypatch) -> None:
    account = await _seed_account(test_session, failure_count=FAILURE_DISABLE_THRESHOLD - 1)

    async def _verify_boom(self: EAAccountService, account_id: int) -> Any:
        raise TimeoutError("EA unreachable")

    monkeypatch.setattr(EAAccountService, "verify", _verify_boom)
    await EAAccountService(test_session).mark_failure(account.persona_id)
    refreshed = await _reload(test_session, account.id)
    assert refreshed.enabled is True
    assert refreshed.failure_count == FAILURE_DISABLE_THRESHOLD
