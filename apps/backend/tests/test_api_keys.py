"""开放 API Key：签发与吊销、按 key 计数限流、管理员调整额度。"""

from __future__ import annotations

from typing import Any

import pytest
from app.api import rate_limit as rate_limit_module
from app.core import ea_budget
from app.core.config import get_settings
from app.db.session import get_db
from app.main import create_app
from app.models import ApiKey
from app.services import api_key_service
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


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
        self.store: dict[str, Any] = {}

    async def incr(self, key: str) -> int:
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]

    async def expire(self, key: str, seconds: int) -> bool:
        return True

    async def get(self, key: str) -> Any:
        value = self.store.get(key)
        return None if value is None else str(value)

    async def mget(self, keys: list[str]) -> list[Any]:
        return [await self.get(k) for k in keys]

    async def set(self, key: str, value: Any, ex: int | None = None, nx: bool = False) -> bool:
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    async def delete(self, key: str) -> int:
        return 1 if self.store.pop(key, None) is not None else 0

    def pipeline(self, transaction: bool = True) -> _FakePipeline:
        return _FakePipeline(self)


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    store = _FakeRedis()

    async def _get() -> _FakeRedis:
        return store

    for module in (rate_limit_module, ea_budget, api_key_service):
        monkeypatch.setattr(module, "get_redis", _get)
    return store


@pytest.fixture
def small_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_lookup_per_minute", 3)
    monkeypatch.setattr(settings, "rate_limit_lookup_per_day", 100)
    monkeypatch.setattr(settings, "rate_limit_api_key_multiplier", 2)
    monkeypatch.setattr(settings, "rate_limit_card_check_per_hour", 2)


def _probe_app(test_session) -> Any:
    app = create_app()
    router = APIRouter()

    @router.get("/lookup", dependencies=[rate_limit_module.rate_limit("lookup")])
    async def _lookup() -> dict[str, bool]:
        return {"ok": True}

    @router.get("/card", dependencies=[rate_limit_module.rate_limit("card_check")])
    async def _card() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(router, prefix="/test")

    async def _override_get_db():
        yield test_session

    app.dependency_overrides[get_db] = _override_get_db
    return app


async def _hit(app: Any, path: str, n: int, key: str | None) -> list[int]:
    headers = {"X-API-Key": key} if key else {}
    transport = ASGITransport(app=app, client=("8.8.8.8", 1))
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as c:
        return [(await c.get(path)).status_code for _ in range(n)]


# ===== 签发与吊销 =====


async def test_create_returns_plaintext_once(user_client, test_session, fake_redis) -> None:
    client, user = user_client
    resp = await client.post("/api/v1/me/api-keys", json={"name": "群机器人"})
    assert resp.status_code == 201
    body = resp.json()
    raw = body["key"]
    assert raw.startswith("bfm_") and len(raw) > 40
    assert body["item"]["prefix"] == raw[:12]

    row = await test_session.scalar(select(ApiKey).where(ApiKey.user_id == user.id))
    assert row is not None and row.key_hash == api_key_service.hash_key(raw)
    assert raw not in row.key_hash

    listed = (await client.get("/api/v1/me/api-keys")).json()
    assert listed["max_keys"] == get_settings().api_key_max_per_user
    assert [i["name"] for i in listed["items"]] == ["群机器人"]
    assert "key" not in listed["items"][0]


async def test_active_key_count_is_capped(user_client, fake_redis, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "api_key_max_per_user", 2)
    client, _ = user_client
    ids = []
    for i in range(2):
        ids.append((await client.post("/api/v1/me/api-keys", json={"name": f"k{i}"})).json())
    assert (await client.post("/api/v1/me/api-keys", json={"name": "k3"})).status_code == 400
    # 吊销一个后可以再建
    await client.post(f"/api/v1/me/api-keys/{ids[0]['item']['id']}/revoke")
    assert (await client.post("/api/v1/me/api-keys", json={"name": "k3"})).status_code == 201


async def test_cannot_touch_other_users_key(user_client, test_session, fake_redis) -> None:
    client, _ = user_client
    other = ApiKey(user_id=12345, name="x", prefix="bfm_xxxxxxxx", key_hash="0" * 64)
    test_session.add(other)
    await test_session.commit()
    assert (await client.post(f"/api/v1/me/api-keys/{other.id}/revoke")).status_code == 404


async def test_admin_routes_require_admin(user_client, fake_redis) -> None:
    client, _ = user_client
    assert (await client.get("/api/v1/admin/api-keys")).status_code == 403


# ===== 按 key 计数 =====


async def test_key_gets_its_own_quota(user_client, test_session, fake_redis, small_limits) -> None:
    client, _ = user_client
    raw = (await client.post("/api/v1/me/api-keys", json={"name": "bot"})).json()["key"]
    app = _probe_app(test_session)

    # 倍数 2：每分钟 6 次；和同 IP 的匿名计数互不影响
    assert await _hit(app, "/test/lookup", 7, raw) == [200] * 6 + [429]
    assert await _hit(app, "/test/lookup", 1, None) == [200]

    listed = (await client.get("/api/v1/me/api-keys")).json()["items"][0]
    assert listed["used_today"] == 7 and listed["used_7d"] == 7
    assert listed["last_used_at"] is not None


async def test_rate_limit_headers(user_client, test_session, fake_redis, small_limits) -> None:
    client, _ = user_client
    raw = (await client.post("/api/v1/me/api-keys", json={"name": "bot"})).json()["key"]
    transport = ASGITransport(app=_probe_app(test_session), client=("8.8.8.8", 1))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/test/lookup", headers={"X-API-Key": raw})
    assert resp.headers["ratelimit-limit"] == "6"
    assert resp.headers["ratelimit-remaining"] == "5"
    assert 1 <= int(resp.headers["ratelimit-reset"]) <= 60


async def test_invalid_or_revoked_key_is_rejected(
    user_client, test_session, fake_redis, small_limits
) -> None:
    client, _ = user_client
    app = _probe_app(test_session)
    assert await _hit(app, "/test/lookup", 1, "bfm_not-a-real-key") == [401]
    assert await _hit(app, "/test/lookup", 1, "garbage") == [401]

    created = (await client.post("/api/v1/me/api-keys", json={"name": "bot"})).json()
    assert await _hit(app, "/test/lookup", 1, created["key"]) == [200]  # 校验结果进了缓存
    await client.post(f"/api/v1/me/api-keys/{created['item']['id']}/revoke")
    assert await _hit(app, "/test/lookup", 1, created["key"]) == [401]


async def test_key_ignored_outside_public_buckets(
    user_client, test_session, fake_redis, small_limits
) -> None:
    """卡行动这类桶不认 key，照旧按 IP 计；无效 key 也不会在这里报 401。"""
    app = _probe_app(test_session)
    assert await _hit(app, "/test/card", 3, "bfm_whatever") == [200, 200, 429]


async def test_admin_can_raise_multiplier(
    admin_client, test_session, fake_redis, small_limits
) -> None:
    client, _ = admin_client
    created = (await client.post("/api/v1/me/api-keys", json={"name": "bot"})).json()
    key_id = created["item"]["id"]
    resp = await client.patch(f"/api/v1/admin/api-keys/{key_id}", json={"rate_multiplier": 3})
    assert resp.status_code == 200 and resp.json()["rate_multiplier"] == 3

    app = _probe_app(test_session)
    assert await _hit(app, "/test/lookup", 10, created["key"]) == [200] * 9 + [429]

    listed = (await client.get("/api/v1/admin/api-keys")).json()
    assert listed["default_multiplier"] == 2
    item = listed["items"][0]
    assert item["custom_multiplier"] is True and item["user_display_name"] == "AdminUser"

    # 管理员吊销后立即失效
    await client.post(f"/api/v1/admin/api-keys/{key_id}/revoke")
    assert await _hit(app, "/test/lookup", 1, created["key"]) == [401]
