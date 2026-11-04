"""BF6：后台凭据保存与刷新、玩家查询接口（上游全部打桩）。"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from app.api.deps import get_session_factory
from app.api.errors import EABusyError
from app.core.security import get_cipher
from app.domain.games.bf6 import client as bf6
from app.domain.games.bf6 import resolver
from app.domain.games.bf6.wire import CategoryStats, Dimension, DimensionedStat, Player, PlayerStats
from app.models import AuditLog
from app.models.bf6_credential import BF6_CREDENTIAL_ID, Bf6Credential
from app.services.bf6 import credential_service, player_service
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

URL = "/api/v1/admin/settings/bf6-credentials"


def _jwt(**claims: Any) -> str:
    def part(data: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")

    return f"{part({'alg': 'none'})}.{part(claims)}.sig"


def _rt(exp_in: int = 9 * 86400, azp: str = bf6.CLIENT_ID) -> str:
    return _jwt(azp=azp, exp=int(time.time()) + exp_in, jti=str(time.time_ns()))


class FakeEA:
    """替身 /connect/token：记录调用参数，每次返回新的 access / refresh token。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.error: bf6.Bf6Error | None = None

    async def __call__(self, client_secret: str, refresh_token: str, *, now: int) -> bf6.TokenGrant:
        self.calls.append((client_secret, refresh_token))
        if self.error:
            raise self.error
        n = len(self.calls)
        return bf6.TokenGrant(
            access_token=f"access-{n}",
            access_expires_at=now + 3 * 86400,
            refresh_token=f"rotated-{n}",
            refresh_expires_at=now + 9 * 86400,
        )


@pytest.fixture
def fake_ea(monkeypatch: pytest.MonkeyPatch) -> FakeEA:
    fake = FakeEA()
    monkeypatch.setattr(bf6, "refresh_access_token", fake)
    credential_service._session.clear()
    return fake


@pytest.fixture
def session_factory(test_session):
    return async_sessionmaker(test_session.bind, expire_on_commit=False)


@pytest.fixture
def admin(admin_client, session_factory):
    client, user = admin_client
    client._transport.app.dependency_overrides[get_session_factory] = lambda: session_factory
    return client, user


async def _row(session_factory) -> Bf6Credential | None:
    async with session_factory() as db:
        return await db.get(Bf6Credential, BF6_CREDENTIAL_ID)


# ---------------------------------------------------------------------------
# 后台保存
# ---------------------------------------------------------------------------


async def test_save_validates_with_ea_and_stores_rotated_token(
    admin, fake_ea: FakeEA, session_factory
) -> None:
    client, _admin = admin
    rt = _rt()

    resp = await client.put(URL, json={"refresh_token": rt})
    assert resp.status_code == 400
    assert "client secret" in resp.json()["error"]["message"]

    resp = await client.put(URL, json={"refresh_token": f"  {rt}\r\n", "client_secret": "sec_1\r"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["configured"] is True
    assert body["last_error"] is None
    assert body["refresh_expires_at"] is not None
    # 粘贴带的空白和 \r 去掉后再发给 EA
    assert fake_ea.calls == [("sec_1", rt)]
    # 接口不回凭据
    assert "rotated" not in resp.text and "sec_1" not in resp.text

    row = await _row(session_factory)
    assert row is not None
    cipher = get_cipher()
    assert cipher.decrypt(row.encrypted_refresh_token) == "rotated-1"
    assert cipher.decrypt(row.encrypted_client_secret) == "sec_1"

    # 只换 refresh token 时沿用已存的 secret
    rt2 = _rt()
    resp = await client.put(URL, json={"refresh_token": rt2})
    assert resp.status_code == 200
    assert fake_ea.calls[-1] == ("sec_1", rt2)

    async with session_factory() as db:
        logs = (await db.scalars(select(AuditLog).where(AuditLog.game == "bf6"))).all()
    assert [log.payload["client_secret_changed"] for log in logs] == [True, False]
    assert all("rotated" not in json.dumps(log.payload) for log in logs)

    status = await client.get(URL)
    assert status.status_code == 200
    assert status.json()["configured"] is True


@pytest.mark.parametrize(
    ("token", "message"),
    [
        ("not-a-jwt-but-long-enough", "格式不对"),
        (_rt(azp="SOME_OTHER_CLIENT"), "不是"),
        (_rt(exp_in=-60), "已过期"),
    ],
)
async def test_save_rejects_bad_token_without_calling_ea(
    admin, fake_ea: FakeEA, token: str, message: str
) -> None:
    client, _ = admin
    resp = await client.put(URL, json={"refresh_token": token, "client_secret": "s"})
    assert resp.status_code == 400
    assert message in resp.json()["error"]["message"]
    assert fake_ea.calls == []


async def test_save_rejected_by_ea_is_not_stored(admin, fake_ea: FakeEA, session_factory) -> None:
    client, _ = admin
    fake_ea.error = bf6.Bf6CredentialError("EA 拒绝了 client secret（invalid_client）")
    resp = await client.put(URL, json={"refresh_token": _rt(), "client_secret": "bad"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "BF6_CREDENTIAL_REJECTED"
    assert await _row(session_factory) is None


async def test_non_admin_cannot_read_status(user_client) -> None:
    client, _ = user_client
    assert (await client.get(URL)).status_code == 403


# ---------------------------------------------------------------------------
# 刷新
# ---------------------------------------------------------------------------


async def _seed(session_factory, *, access_left: int, refreshed_ago: int = 0) -> None:
    cipher = get_cipher()
    now = datetime.now(UTC)
    async with session_factory() as db:
        db.add(
            Bf6Credential(
                id=BF6_CREDENTIAL_ID,
                encrypted_client_secret=cipher.encrypt("sec"),
                encrypted_refresh_token=cipher.encrypt("rt-0"),
                encrypted_access_token=cipher.encrypt("access-0"),
                access_expires_at=now + timedelta(seconds=access_left),
                last_refreshed_at=now - timedelta(seconds=refreshed_ago),
            )
        )
        await db.commit()


async def test_access_token_cached_until_near_expiry(fake_ea: FakeEA, session_factory) -> None:
    await _seed(session_factory, access_left=86400)
    assert await credential_service.get_access_token(session_factory) == "access-0"
    assert fake_ea.calls == []


async def test_expiring_access_token_refreshes_and_rotates(
    fake_ea: FakeEA, session_factory
) -> None:
    await _seed(session_factory, access_left=60)
    assert await credential_service.get_access_token(session_factory) == "access-1"
    assert fake_ea.calls == [("sec", "rt-0")]
    row = await _row(session_factory)
    assert row is not None
    assert get_cipher().decrypt(row.encrypted_refresh_token) == "rotated-1"
    # 刚刷新过，下一次直接用库里的
    assert await credential_service.get_access_token(session_factory) == "access-1"
    assert len(fake_ea.calls) == 1


async def test_daily_refresh_even_if_access_still_valid(fake_ea: FakeEA, session_factory) -> None:
    await _seed(session_factory, access_left=2 * 86400, refreshed_ago=25 * 3600)
    token = await credential_service.get_access_token(session_factory, max_age=86400)
    assert token == "access-1"
    assert fake_ea.calls == [("sec", "rt-0")]


async def test_refresh_failure_is_recorded(fake_ea: FakeEA, session_factory) -> None:
    await _seed(session_factory, access_left=0)
    fake_ea.error = bf6.Bf6CredentialError("refresh token 已失效或已被轮换（invalid_grant）")
    with pytest.raises(bf6.Bf6CredentialError):
        await credential_service.get_access_token(session_factory)
    row = await _row(session_factory)
    assert row is not None
    assert row.last_error is not None and "invalid_grant" in row.last_error
    # 失败时不动已存的 refresh token
    assert get_cipher().decrypt(row.encrypted_refresh_token) == "rt-0"


async def test_not_configured(session_factory) -> None:
    with pytest.raises(credential_service.Bf6NotConfiguredError):
        await credential_service.get_access_token(session_factory)


# ---------------------------------------------------------------------------
# 玩家查询接口
# ---------------------------------------------------------------------------


@pytest.fixture
def memory_cache(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    store: dict[str, Any] = {}

    async def get(key: str) -> Any:
        return store.get(key)

    async def set_(key: str, value: Any, ttl: int) -> None:
        store[key] = value

    monkeypatch.setattr(player_service, "_cache_get", get)
    monkeypatch.setattr(player_service, "_cache_set", set_)
    return store


@pytest.fixture
def api(client, session_factory):
    client._transport.app.dependency_overrides[get_session_factory] = lambda: session_factory
    return client


def _player(nucleus_id: int) -> PlayerStats:
    rows = tuple(
        DimensionedStat(name, value, (Dimension("global", "global"),))
        for name, value in [("Kills_Total", 10), ("human_kills_total", 8), ("deaths_total", 4)]
    )
    return PlayerStats(
        player=Player(nucleus_id=nucleus_id, platform=7),
        categories=(CategoryStats("glacier_mp", dimensioned_stats=rows),),
    )


async def test_stats_endpoint_renews_rejected_session_once(
    api, monkeypatch: pytest.MonkeyPatch, memory_cache: dict[str, Any]
) -> None:
    sessions: list[bool] = []
    calls: list[str] = []

    async def session_jwt(_sf, *, renew: bool = False) -> str:
        sessions.append(renew)
        return "fresh" if renew else "stale"

    async def get_stats(token: str, ids: list[int]) -> list[PlayerStats]:
        calls.append(token)
        if token == "stale":
            raise bf6.Bf6SessionExpiredError("expired")
        return [_player(ids[0])]

    monkeypatch.setattr(credential_service, "get_session_jwt", session_jwt)
    monkeypatch.setattr(bf6, "get_stats", get_stats)

    resp = await api.get("/api/v1/bf6/players/1008067890273/stats")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["has_data"] is True
    assert body["career"]["kills"] == 10
    assert body["career"]["kd"] == 2.0
    assert sessions == [False, True]
    assert calls == ["stale", "fresh"]

    # 第二次走缓存
    resp = await api.get("/api/v1/bf6/players/1008067890273/stats")
    assert resp.status_code == 200
    assert calls == ["stale", "fresh"]


async def test_stats_endpoint_hides_credential_problems(
    api, monkeypatch: pytest.MonkeyPatch, memory_cache: dict[str, Any]
) -> None:
    async def session_jwt(_sf, *, renew: bool = False) -> str:
        raise credential_service.Bf6NotConfiguredError("后台还没有填写 BF6 凭据")

    monkeypatch.setattr(credential_service, "get_session_jwt", session_jwt)
    resp = await api.get("/api/v1/bf6/players/42/stats")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "BF6_UNAVAILABLE"
    assert "后台" not in resp.json()["error"]["message"]
    assert memory_cache == {}


async def test_resolve_endpoint_and_negative_cache(
    api, monkeypatch: pytest.MonkeyPatch, memory_cache: dict[str, Any]
) -> None:
    lookups: list[tuple[str, str | None]] = []

    async def fetch_event(_http) -> str:
        return "EVT"

    async def lookup(_http, name: str, event: str, platform):
        lookups.append((name, platform))
        if name == "JackFrags":
            return resolver.ResolvedPlayer(2306831843, "JackFrags", "cem_ea_id", None, True)
        return None

    monkeypatch.setattr(resolver, "fetch_current_event", fetch_event)
    monkeypatch.setattr(resolver, "lookup", lookup)

    resp = await api.get(
        "/api/v1/bf6/players/resolve", params={"name": " JackFrags ", "platform": "ea"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["nucleus_id"] == 2306831843
    assert lookups == [("JackFrags", "ea")]

    resp = await api.get("/api/v1/bf6/players/resolve", params={"name": "nobody"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "BF6_PLAYER_NOT_FOUND"
    # 不存在的名字缓存 10 分钟，不再打上游
    resp = await api.get("/api/v1/bf6/players/resolve", params={"name": "NOBODY"})
    assert resp.status_code == 422
    assert lookups.count(("nobody", None)) == 1
    assert ("NOBODY", None) not in lookups

    resp = await api.get(
        "/api/v1/bf6/players/resolve", params={"name": "x", "platform": "nintendo"}
    )
    assert resp.status_code == 422


async def test_invalid_input_is_not_echoed(admin, fake_ea: FakeEA) -> None:
    client, _ = admin
    for body in (
        {"refresh_token": "SENSITIVE_TOKEN", "client_secret": "SENSITIVE_SECRET"},
        {"refresh_token": "SENSITIVE_" * 2000, "client_secret": "s"},
        {"refresh_token": _rt(), "client_secret": "SENSITIVE_SECRET" * 40},
    ):
        resp = await client.put(URL, json=body)
        assert resp.status_code == 400
        assert "SENSITIVE" not in resp.text
    assert fake_ea.calls == []


# ---------------------------------------------------------------------------
# 轮换后的 token 不能丢
# ---------------------------------------------------------------------------


async def test_cancelled_caller_does_not_lose_rotated_token(
    monkeypatch: pytest.MonkeyPatch, session_factory
) -> None:
    await _seed(session_factory, access_left=0)
    release = asyncio.Event()
    calls: list[str] = []

    async def slow_ea(client_secret: str, refresh_token: str, *, now: int) -> bf6.TokenGrant:
        calls.append(refresh_token)
        await release.wait()
        return bf6.TokenGrant("access-new", now + 86400, "rotated-new", now + 9 * 86400)

    monkeypatch.setattr(bf6, "refresh_access_token", slow_ea)
    caller = asyncio.create_task(credential_service.get_access_token(session_factory))
    while not calls:
        await asyncio.sleep(0)
    # 停机时 poller 被 cancel：EA 那边已经在轮换
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    release.set()
    await credential_service.drain()

    row = await _row(session_factory)
    assert row is not None
    assert get_cipher().decrypt(row.encrypted_refresh_token) == "rotated-new"


async def test_commit_failure_retries_with_same_grant(
    fake_ea: FakeEA, monkeypatch: pytest.MonkeyPatch, session_factory
) -> None:
    await _seed(session_factory, access_left=0)
    original = AsyncSession.commit
    failures = {"left": 1}

    async def flaky_commit(self: AsyncSession) -> None:
        if failures["left"]:
            failures["left"] -= 1
            raise OperationalError("COMMIT", {}, Exception("connection reset"))
        await original(self)

    monkeypatch.setattr(AsyncSession, "commit", flaky_commit)
    monkeypatch.setattr(credential_service.asyncio, "sleep", _no_sleep)
    assert await credential_service.get_access_token(session_factory) == "access-1"
    # 只找 EA 换了一次，写库重试用的是同一份新 token
    assert fake_ea.calls == [("sec", "rt-0")]
    row = await _row(session_factory)
    assert row is not None
    assert get_cipher().decrypt(row.encrypted_refresh_token) == "rotated-1"


async def _no_sleep(_seconds: float) -> None:
    return None


# ---------------------------------------------------------------------------
# 上游响应异常
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="<html>maintenance</html>"),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={"access_token": "a", "refresh_token": "r", "expires_in": "bad"}),
        httpx.Response(200, json={"refresh_token": "r"}),
        httpx.Response(502, text="<html>bad gateway</html>"),
    ],
)
async def test_malformed_token_response_is_upstream_error(response: httpx.Response) -> None:
    transport = httpx.MockTransport(lambda _request: response)
    async with httpx.AsyncClient(transport=transport) as http:
        with pytest.raises(bf6.Bf6Error) as exc:
            await bf6.refresh_access_token("s", "r", now=0, http=http)
    assert not isinstance(exc.value, bf6.Bf6CredentialError)
    assert "maintenance" not in str(exc.value)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="<html>"),
        httpx.Response(200, json=[1]),
        httpx.Response(200, json={"playerStatsSummary": {"userId": "abc"}}),
    ],
)
async def test_malformed_drop_api_response_is_upstream_error(response: httpx.Response) -> None:
    transport = httpx.MockTransport(lambda _request: response)
    async with httpx.AsyncClient(transport=transport) as http:
        with pytest.raises(bf6.Bf6Error):
            await resolver.lookup(http, "x", "EVT", None)


async def test_malformed_refresh_is_recorded(
    monkeypatch: pytest.MonkeyPatch, session_factory
) -> None:
    await _seed(session_factory, access_left=0)

    async def broken(client_secret: str, refresh_token: str, *, now: int) -> bf6.TokenGrant:
        raise bf6.Bf6Error("EA 换 token 的响应不是 JSON")

    monkeypatch.setattr(bf6, "refresh_access_token", broken)
    with pytest.raises(bf6.Bf6Error):
        await credential_service.get_access_token(session_factory)
    row = await _row(session_factory)
    assert row is not None and row.last_error == "EA 换 token 的响应不是 JSON"


# ---------------------------------------------------------------------------
# 公共预算
# ---------------------------------------------------------------------------


async def test_resolve_respects_public_budget(
    api, monkeypatch: pytest.MonkeyPatch, memory_cache: dict[str, Any]
) -> None:
    upstream: list[str] = []

    async def fetch_event(_http) -> str:
        upstream.append("event")
        return "EVT"

    async def lookup(_http, name, event, platform):
        upstream.append("lookup")

    async def exhausted() -> None:
        raise EABusyError(30)

    monkeypatch.setattr(resolver, "fetch_current_event", fetch_event)
    monkeypatch.setattr(resolver, "lookup", lookup)
    monkeypatch.setattr(player_service.ea_budget, "acquire", exhausted)
    resp = await api.get("/api/v1/bf6/players/resolve", params={"name": "someone"})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "EA_BUSY"
    assert upstream == []
