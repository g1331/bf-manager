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

    async def fake_post(body):
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

    async def fake_post(body):
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


class _LoginResponse:
    """模拟 accounts.ea.com 对 remid/sid 的应答。"""

    def __init__(self, body: str, set_cookie: str = "") -> None:
        self._body = body
        self.headers = {"Set-Cookie": set_cookie} if set_cookie else {}

    async def text(self) -> str:
        return self._body


async def _run_login(resp: _LoginResponse) -> tuple[BF1GatewayClient, object, str]:
    from loguru import logger

    client = BF1GatewayClient(pid=7)

    async def _get(**kwargs):
        return resp

    client.http_session = SimpleNamespace(get=_get, close=None)  # type: ignore[assignment]
    lines: list[str] = []
    sink_id = logger.add(lambda m: lines.append(str(m)), level="DEBUG")
    try:
        result = await client.login("remid-secret", "sid-secret")
    finally:
        logger.remove(sink_id)
    return client, result, "".join(lines)


@pytest.mark.asyncio
async def test_login_required_fails_cleanly_without_auto_login():
    """凭据失效：不再去读磁盘账密自动重登，直接失败并提示去后台重新登录。"""
    client, result, logs = await _run_login(_LoginResponse('{"error":"login_required"}'))
    assert client.check_login is False
    assert result == '{"error":"login_required"}'
    assert "需要在后台用邮箱密码重新登录" in logs
    assert "No such file" not in logs
    assert "remid-secret" not in logs and "sid-secret" not in logs


@pytest.mark.asyncio
async def test_login_logs_never_contain_token_or_sid(monkeypatch):
    """access_token 换取成功（随后 authcode 步骤失败）全程日志不得出现凭据值。"""

    class _NoNetwork:
        def __init__(self, **kwargs) -> None:
            raise ConnectionError("network disabled in unit test")

    monkeypatch.setattr("app.domain.games.bf1.gateway.httpx.AsyncClient", _NoNetwork)
    _, _, logs = await _run_login(
        _LoginResponse(
            '{"access_token":"tok-secret","expires_in":3600}',
            set_cookie="sid=sid-refreshed-secret; Path=/",
        )
    )
    for secret in ("tok-secret", "sid-refreshed-secret", "remid-secret", "sid-secret"):
        assert secret not in logs
