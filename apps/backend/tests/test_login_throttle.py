"""本地登录防爆破与统一错误响应：失败计数、锁定与 429、成功清零、Redis 故障放行、request_id。"""

from __future__ import annotations

from typing import Any

import pytest
from app.api.errors import TooManyRequestsError
from app.main import create_app
from app.services import login_throttle
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return str(self.store[key]) if key in self.store else None

    async def incr(self, key: str) -> int:
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    async def expire(self, key: str, seconds: int) -> None:
        self.ttls[key] = seconds

    async def ttl(self, key: str) -> int:
        return self.ttls.get(key, -1)

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            removed += int(self.store.pop(key, None) is not None)
            self.ttls.pop(key, None)
        return removed


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    store = _FakeRedis()

    async def _get() -> _FakeRedis:
        return store

    monkeypatch.setattr(login_throttle, "get_redis", _get)
    return store


async def test_locks_username_after_max_failures(fake_redis: _FakeRedis) -> None:
    for _ in range(login_throttle.MAX_FAILURES_PER_USER):
        await login_throttle.ensure_not_locked("Root", "1.2.3.4")
        await login_throttle.record_failure("Root", "1.2.3.4")

    # 用户名大小写不同视为同一账号，不能借此绕过
    with pytest.raises(TooManyRequestsError) as exc_info:
        await login_throttle.ensure_not_locked("root", "5.6.7.8")
    assert exc_info.value.status_code == 429
    assert exc_info.value.headers == {"Retry-After": str(login_throttle.WINDOW_SECONDS)}
    assert "15 分钟" in exc_info.value.message


async def test_window_starts_at_first_failure(fake_redis: _FakeRedis) -> None:
    await login_throttle.record_failure("root", None)
    fake_redis.ttls[login_throttle._user_key("root")] = 100
    await login_throttle.record_failure("root", None)
    assert fake_redis.ttls[login_throttle._user_key("root")] == 100


async def test_locks_ip_across_usernames(fake_redis: _FakeRedis) -> None:
    for i in range(login_throttle.MAX_FAILURES_PER_IP):
        await login_throttle.record_failure(f"user{i}", "1.2.3.4")
    with pytest.raises(TooManyRequestsError):
        await login_throttle.ensure_not_locked("someone-else", "1.2.3.4")
    await login_throttle.ensure_not_locked("someone-else", "9.9.9.9")


async def test_success_clears_username_but_keeps_ip(fake_redis: _FakeRedis) -> None:
    await login_throttle.record_failure("root", "1.2.3.4")
    await login_throttle.clear("root")
    assert login_throttle._user_key("root") not in fake_redis.store
    assert fake_redis.store[login_throttle._ip_key("1.2.3.4")] == 1


async def test_redis_failure_lets_login_through(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _broken() -> Any:
        raise ConnectionError("redis down")

    monkeypatch.setattr(login_throttle, "get_redis", _broken)
    await login_throttle.ensure_not_locked("root", "1.2.3.4")
    await login_throttle.record_failure("root", "1.2.3.4")
    await login_throttle.clear("root")


async def test_local_login_returns_429_when_locked(fake_redis: _FakeRedis) -> None:
    fake_redis.store[login_throttle._user_key("root")] = login_throttle.MAX_FAILURES_PER_USER
    fake_redis.ttls[login_throttle._user_key("root")] = 120
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/local-login", json={"username": "root", "password": "whatever"}
        )
    assert resp.status_code == 429
    assert resp.headers["retry-after"] == "120"
    body = resp.json()["error"]
    assert body["code"] == "TOO_MANY_REQUESTS"
    assert body["message"] == "登录失败次数过多，请 2 分钟后再试"
    assert body["request_id"] == resp.headers["x-request-id"]


async def test_unhandled_error_hides_exception_text() -> None:
    app: FastAPI = create_app()

    @app.get("/boom")
    async def _boom() -> None:
        raise RuntimeError("secret internal detail")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/boom")
    assert resp.status_code == 500
    body = resp.json()["error"]
    assert body["code"] == "INTERNAL_ERROR"
    assert "secret" not in resp.text
    assert isinstance(body["request_id"], str) and len(body["request_id"]) == 12
