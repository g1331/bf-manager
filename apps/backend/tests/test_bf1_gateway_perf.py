"""EA 登录态复用、session 失效重放、生涯战绩缓存

这三处决定玩家列表等接口的往返次数：登录态跨请求复用省掉每次 4 次登录往返；
复用的 session 被 EA 提前作废时须自动重登并重放；战绩命中缓存时不再查询 EA。
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from app.domain.games.bf1.gateway import BF1GatewayClient
from app.services.bf1 import blaze_service, gateway_factory


@pytest.fixture(autouse=True)
def _clear_login_states():
    gateway_factory._login_states.clear()
    yield
    gateway_factory._login_states.clear()


def _logged_in(**overrides) -> SimpleNamespace:
    state = {
        "sid": "sid-1",
        "session": "sess-1",
        "check_login": True,
        "access_token": "tok-1",
        "access_token_time": time.time(),
        "access_token_expires_time": 3600,
        "desktop_access_token": None,
        "desktop_access_token_expires_at": 0.0,
    }
    state.update(overrides)
    return SimpleNamespace(**state)


def test_login_state_round_trip():
    gateway_factory._save_login_state(_logged_in(), 1, "remid")
    fresh = SimpleNamespace(access_token=None)
    gateway_factory._restore_login_state(fresh, 1, "remid")
    assert fresh.access_token == "tok-1"
    assert fresh.session == "sess-1"


def test_login_state_not_shared_across_remid():
    gateway_factory._save_login_state(_logged_in(), 1, "old-remid")
    fresh = SimpleNamespace(access_token=None)
    gateway_factory._restore_login_state(fresh, 1, "new-remid")
    assert fresh.access_token is None


def test_expired_login_state_is_dropped():
    gateway_factory._save_login_state(_logged_in(access_token_time=time.time() - 3590), 1, "r")
    fresh = SimpleNamespace(access_token=None)
    gateway_factory._restore_login_state(fresh, 1, "r")
    assert fresh.access_token is None
    assert (1, "r") not in gateway_factory._login_states


def test_failed_session_is_not_cached():
    gateway_factory._save_login_state(_logged_in(), 1, "r")
    gateway_factory._save_login_state(_logged_in(check_login=False), 1, "r")
    assert (1, "r") not in gateway_factory._login_states


@pytest.mark.asyncio
async def test_api_call_relogins_and_replays_on_invalid_session():
    client = BF1GatewayClient(pid=1, remid="remid", sid="sid", session="stale")
    client.check_login = True
    responses = [
        {"error": {"code": -32501, "message": "Invalid Params: no valid session"}},
        {"result": {"ok": True}},
    ]
    sent_sessions: list[str] = []

    async def fake_post(body, proxied=False):
        sent_sessions.append(client.session)
        return responses.pop(0)

    async def fake_login(remid, sid):
        client.session = "fresh"
        client.check_login = True
        return "fresh"

    client._post_jsonrpc = fake_post
    client.login = fake_login
    try:
        res = await client.api_call({"method": "x"})
    finally:
        await client.http_session.close()
    assert res == {"result": {"ok": True}}
    assert sent_sessions == ["stale", "fresh"]


@pytest.mark.asyncio
async def test_api_call_does_not_replay_when_relogin_fails():
    client = BF1GatewayClient(pid=1, remid="remid", sid="sid", session="stale")
    calls = 0

    async def fake_post(body, proxied=False):
        nonlocal calls
        calls += 1
        return {"error": {"code": -32501, "message": "Invalid Params: no valid session"}}

    async def fake_login(remid, sid):
        return "login failed"

    client._post_jsonrpc = fake_post
    client.login = fake_login
    try:
        res = await client.api_call({"method": "x"})
    finally:
        await client.http_session.close()
    assert isinstance(res, str)
    assert calls == 1


class _FakeCache:
    def __init__(self) -> None:
        self.data: dict[str, dict] = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, ttl=None):
        self.data[key] = value


class _FakeStatsClient:
    def __init__(self) -> None:
        self.queried: list[int] = []

    async def detailedStatsByPersonaId(self, pid):  # noqa: N802
        self.queried.append(pid)
        basic = {"kills": 10, "deaths": 5, "wins": 3, "losses": 1, "timePlayed": 7200}
        return {"result": {"basicStats": {**basic, "kpm": 1.0, "spm": 500, "extra": "x"}}}


@pytest.mark.asyncio
async def test_gather_stats_uses_cache_on_second_call(monkeypatch):
    cache = _FakeCache()

    async def fake_stats_cache():
        return cache

    monkeypatch.setattr(blaze_service, "_stats_cache", fake_stats_cache)
    client = _FakeStatsClient()

    first, _ = await blaze_service._gather_stats(client, [1, 2])
    second, ranks = await blaze_service._gather_stats(client, [1, 2])

    assert client.queried == [1, 2]
    assert second == first
    assert second[1].kd == 2.0
    assert set(ranks) == {1, 2}
    assert "extra" not in cache.data[f"{blaze_service.STATS_CACHE_PREFIX}:1"]
