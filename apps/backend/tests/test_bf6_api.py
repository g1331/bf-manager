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
    """替身 /connect/token：记录调用参数，每次返回新的 access / refresh token。

    和真的一样，refresh token 只能用一次，再拿用过的去换会被拒。
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.error: bf6.Bf6Error | None = None
        self.used: set[str] = set()

    async def __call__(self, client_secret: str, refresh_token: str, *, now: int) -> bf6.TokenGrant:
        self.calls.append((client_secret, refresh_token))
        if self.error:
            raise self.error
        if refresh_token in self.used:
            raise bf6.Bf6CredentialError("refresh token 已失效或已被轮换（invalid_grant）")
        self.used.add(refresh_token)
        n = len(self.calls)
        return bf6.TokenGrant(
            access_token=f"access-{n}",
            access_expires_at=now + 3 * 86400,
            refresh_token=f"rotated-{n}",
            refresh_expires_at=now + 9 * 86400,
        )


class FakeCache:
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}

    async def get(self, key: str) -> Any:
        return self.store.get(key)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        self.store[key] = value

    async def delete(self, *keys: str) -> int:
        return sum(self.store.pop(k, None) is not None for k in keys)

    async def hash_set(self, key: str, field: str, value: str, *, ttl: int | None = None) -> None:
        self.store.setdefault(key, {})[field] = value

    async def hash_all(self, key: str) -> dict[str, str]:
        return dict(self.store.get(key, {}))

    async def hash_delete(self, key: str, *fields: str) -> int:
        h = self.store.get(key, {})
        n = sum(h.pop(f, None) is not None for f in fields)
        if not h:
            self.store.pop(key, None)
        return n


@pytest.fixture(autouse=True)
def stash(monkeypatch: pytest.MonkeyPatch) -> FakeCache:
    """凭据服务存待补写 token 用的 Redis，换成内存；每个用例从干净的进程状态开始。"""
    cache = FakeCache()

    async def get_cache() -> FakeCache:
        return cache

    monkeypatch.setattr(credential_service, "get_cache", get_cache)
    monkeypatch.setattr(credential_service, "_unsaved", {})
    monkeypatch.setattr(credential_service, "_refreshing", None)
    return cache


@pytest.fixture
def fake_ea(monkeypatch: pytest.MonkeyPatch) -> FakeEA:
    fake = FakeEA()
    monkeypatch.setattr(bf6, "refresh_access_token", fake)
    credential_service._session.clear()
    return fake


@pytest.fixture
def session_factory(test_session):
    # 和生产的会话配置一致：不自动 flush
    return async_sessionmaker(test_session.bind, expire_on_commit=False, autoflush=False)


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


async def test_stats_catalog_metadata_on_fresh_and_cached_responses(
    api, monkeypatch: pytest.MonkeyPatch, memory_cache: dict[str, Any]
) -> None:
    expected = {
        "weapons": ("mg_l110", "L110", "/bf6/weapons/mg_l110.webp"),
        "weapon_categories": ("mg", "机枪", None),
        "vehicles": ("air_uh06", "UH-06", None),
        "vehicle_categories": ("sur", "地面载具", None),
        "gadgets": ("c4", "C-4 炸药", "/bf6/gadgets/c4.webp"),
        "kits": ("assault", "突击兵", "/bf6/classes/assault-wide.webp"),
        "modes": ("op", "Operations", "/bf6/modes/op.svg"),
        "maps": ("mpaftermath", "帝国之州", "/bf6/maps/mpaftermath.webp"),
    }
    values = {
        "kw_wp_mg_l110": 10,
        "kw_wp_mg": 10,
        "kw_wp_new_weapon": 5,
        "kw_veh_air_uh06": 2,
        "kw_veh_sur": 3,
        "kw_gad_c4": 4,
        "tp_kit_assault": 100,
        "matches_gm_op": 1,
        "matches_lvlmpaftermath": 1,
    }
    calls = 0

    async def session_jwt(_sf, *, renew: bool = False) -> str:
        return "token"

    async def get_stats(token: str, ids: list[int]) -> list[PlayerStats]:
        nonlocal calls
        calls += 1
        rows = tuple(
            DimensionedStat(name, value, (Dimension("global", "global"),))
            for name, value in values.items()
        )
        return [
            PlayerStats(
                Player(nucleus_id=ids[0], platform=7),
                (CategoryStats("glacier_mp", dimensioned_stats=rows),),
            )
        ]

    monkeypatch.setattr(credential_service, "get_session_jwt", session_jwt)
    monkeypatch.setattr(bf6, "get_stats", get_stats)
    for _ in range(2):
        resp = await api.get("/api/v1/bf6/players/42/stats")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        for section, (item_id, name, image) in expected.items():
            item = next(row for row in body[section] if row["id"] == item_id)
            assert (item["name"], item["image"]) == (name, image)
        unknown = next(row for row in body["weapons"] if row["id"] == "new_weapon")
        assert unknown["name"] is None and unknown["image"] is None
        assert unknown["kills"] == 5
        # 模拟上线前写入的缓存，没有展示字段也能补全。
        for cached in memory_cache.values():
            for section in expected:
                for item in cached.get(section, []):
                    item.pop("name", None)
                    item.pop("image", None)
    assert calls == 1


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
    # 类型不对走的是参数校验（422），同样不能带回原文
    for body in (
        {"refresh_token": ["SENSITIVE_TOKEN"], "client_secret": {"secret": "SENSITIVE_SECRET"}},
        ["SENSITIVE_TOKEN"],
    ):
        resp = await client.put(URL, json=body)
        assert resp.status_code == 422
        assert "SENSITIVE" not in resp.text
        assert resp.json()["detail"][0]["loc"][0] == "body"
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


def _fail_commits(monkeypatch: pytest.MonkeyPatch, *, after_commit: bool = False) -> dict[str, int]:
    """让 commit 失败 left 次；after_commit=True 时先真的提交再报错（提交确认丢失）。"""
    original = AsyncSession.commit
    state = {"left": 0}

    async def commit(self: AsyncSession) -> None:
        if state["left"]:
            state["left"] -= 1
            if after_commit:
                await original(self)
            raise OperationalError("COMMIT", {}, Exception("connection reset"))
        await original(self)

    monkeypatch.setattr(AsyncSession, "commit", commit)
    monkeypatch.setattr(credential_service.asyncio, "sleep", _no_sleep)
    return state


async def test_exhausted_retries_keep_rotated_token_for_next_process(
    fake_ea: FakeEA, monkeypatch: pytest.MonkeyPatch, session_factory, stash: FakeCache
) -> None:
    await _seed(session_factory, access_left=0)
    failing = _fail_commits(monkeypatch)
    failing["left"] = 100
    with pytest.raises(OperationalError):
        await credential_service.get_access_token(session_factory)
    assert credential_service._UNSAVED_KEY in stash.store

    # 数据库恢复、进程也换了（内存里那份没了），只剩 Redis 里的
    failing["left"] = 0
    monkeypatch.setattr(credential_service, "_unsaved", {})
    assert await credential_service.get_access_token(session_factory) == "access-1"
    # 没有再拿作废的 rt-0 去换
    assert fake_ea.calls == [("sec", "rt-0")]
    row = await _row(session_factory)
    assert row is not None
    assert get_cipher().decrypt(row.encrypted_refresh_token) == "rotated-1"
    assert stash.store == {}


async def test_drain_timeout_leaves_grant_in_redis(
    fake_ea: FakeEA, monkeypatch: pytest.MonkeyPatch, session_factory, stash: FakeCache
) -> None:
    await _seed(session_factory, access_left=0)
    original = AsyncSession.commit
    blocked = asyncio.Event()

    async def stuck_commit(self: AsyncSession) -> None:
        blocked.set()
        await asyncio.Event().wait()  # 数据库卡住，永远等不到

    monkeypatch.setattr(AsyncSession, "commit", stuck_commit)
    caller = asyncio.create_task(credential_service.get_access_token(session_factory))
    await blocked.wait()
    await credential_service.drain(timeout=0.01)
    assert credential_service._UNSAVED_KEY in stash.store

    # 事件循环退出：卡住的任务被取消；重启后从 Redis 补写
    for task in list(credential_service._pending):
        task.cancel()
    caller.cancel()
    await asyncio.gather(caller, *credential_service._pending, return_exceptions=True)
    monkeypatch.setattr(AsyncSession, "commit", original)
    monkeypatch.setattr(credential_service, "_unsaved", {})
    monkeypatch.setattr(credential_service, "_refreshing", None)
    assert await credential_service.get_access_token(session_factory) == "access-1"
    assert fake_ea.calls == [("sec", "rt-0")]


async def test_lost_commit_ack_is_not_written_twice(
    fake_ea: FakeEA, monkeypatch: pytest.MonkeyPatch, session_factory
) -> None:
    await _seed(session_factory, access_left=0)
    _fail_commits(monkeypatch, after_commit=True)["left"] = 1
    assert await credential_service.get_access_token(session_factory) == "access-1"
    row = await _row(session_factory)
    assert row is not None
    assert row.generation == 1
    assert get_cipher().decrypt(row.encrypted_refresh_token) == "rotated-1"


async def test_stale_retry_does_not_override_newer_admin_save(
    admin, fake_ea: FakeEA, session_factory
) -> None:
    client, _ = admin
    await _seed(session_factory, access_left=0)
    # 后台刷新换到了 rotated-x，第一次 commit 失败、还没来得及重试
    stale = credential_service._Unsaved(
        bf6.TokenGrant("access-x", int(time.time()) + 86400, "rotated-x", None),
        base_generation=0,
        created_at=time.time(),
    )
    # 这时管理员保存了新凭据
    resp = await client.put(URL, json={"refresh_token": _rt(), "client_secret": "new-secret"})
    assert resp.status_code == 200
    await credential_service._persist_grant(session_factory, stale)

    row = await _row(session_factory)
    assert row is not None
    cipher = get_cipher()
    assert cipher.decrypt(row.encrypted_client_secret) == "new-secret"
    assert cipher.decrypt(row.encrypted_refresh_token) == "rotated-1"


async def test_cancelled_save_still_writes_audit_and_drops_old_session(
    admin, monkeypatch: pytest.MonkeyPatch, session_factory
) -> None:
    _client, user = admin
    await _seed(session_factory, access_left=86400)
    credential_service._session.token, credential_service._session.expires_at = "old", 2**31
    release = asyncio.Event()

    async def slow_ea(client_secret: str, refresh_token: str, *, now: int) -> bf6.TokenGrant:
        await release.wait()
        return bf6.TokenGrant("access-new", now + 86400, "rotated-new", now + 9 * 86400)

    monkeypatch.setattr(bf6, "refresh_access_token", slow_ea)
    save = asyncio.create_task(
        credential_service.save_credentials(
            session_factory, refresh_token=_rt(), client_secret=None, actor=user, ip="1.2.3.4"
        )
    )
    while not credential_service._pending:
        await asyncio.sleep(0)
    save.cancel()
    with pytest.raises(asyncio.CancelledError):
        await save
    release.set()
    await credential_service.drain()

    row = await _row(session_factory)
    assert row is not None
    assert get_cipher().decrypt(row.encrypted_refresh_token) == "rotated-new"
    assert row.updated_by == user.id
    async with session_factory() as db:
        logs = (await db.scalars(select(AuditLog).where(AuditLog.game == "bf6"))).all()
    assert len(logs) == 1 and logs[0].ip == "1.2.3.4"
    assert credential_service._session.token == ""


async def test_admin_save_commit_ack_lost_writes_one_audit(
    admin, fake_ea: FakeEA, monkeypatch: pytest.MonkeyPatch, session_factory
) -> None:
    client, _ = admin
    await _seed(session_factory, access_left=86400)
    _fail_commits(monkeypatch, after_commit=True)["left"] = 1
    resp = await client.put(URL, json={"refresh_token": _rt()})
    assert resp.status_code == 200, resp.text
    row = await _row(session_factory)
    assert row is not None
    assert row.generation == 1
    async with session_factory() as db:
        logs = (await db.scalars(select(AuditLog).where(AuditLog.game == "bf6"))).all()
    assert len(logs) == 1


def _admin_req(
    user, write_id: str = "w-1", after_audit: int = 0
) -> credential_service._SaveRequest:
    return credential_service._SaveRequest(
        refresh_token=_rt(),
        client_secret="new-secret",
        admin=credential_service._AdminWrite(
            actor_id=user.id,
            persona_id=0,
            ip="1.2.3.4",
            secret_changed=True,
            write_id=write_id,
            after_audit=after_audit,
        ),
    )


def _admin_grant(rt: str = "admin-rotated", access_left: int = 86400) -> bf6.TokenGrant:
    return bf6.TokenGrant("admin-access", int(time.time()) + access_left, rt, None)


async def _audits(session_factory) -> list[AuditLog]:
    async with session_factory() as db:
        return list(await db.scalars(select(AuditLog).where(AuditLog.game == "bf6")))


async def test_admin_cleanup_keeps_newer_refresh_grant(
    admin, fake_ea: FakeEA, monkeypatch: pytest.MonkeyPatch, session_factory, stash: FakeCache
) -> None:
    _client, user = admin
    await _seed(session_factory, access_left=0)
    entered, release = asyncio.Event(), asyncio.Event()
    original_forget = credential_service._forget

    async def paused_forget(unsaved: credential_service._Unsaved) -> None:
        if unsaved.admin is not None and not entered.is_set():
            entered.set()
            await release.wait()
        await original_forget(unsaved)

    monkeypatch.setattr(credential_service, "_forget", paused_forget)
    # 管理员保存已提交、还没清理自己那份；access token 快过期，紧接着就会刷新
    task = asyncio.create_task(
        credential_service._store_admin_grant(
            session_factory, _admin_req(user), _admin_grant(access_left=60)
        )
    )
    await entered.wait()
    failing = _fail_commits(monkeypatch)
    failing["left"] = 100
    # 刷新把 admin-rotated 换成 rotated-1，但写库一直失败
    with pytest.raises(OperationalError):
        await credential_service.get_access_token(session_factory)
    release.set()
    await task

    # 管理员保存的清理只删自己那份，刷新换到的新 token 还在
    assert len(stash.store[credential_service._UNSAVED_KEY]) == 1
    failing["left"] = 0
    await credential_service.get_access_token(session_factory, max_age=0)
    assert fake_ea.calls[-1][1] == "rotated-1"
    assert stash.store == {}


async def test_admin_grant_is_backed_up_before_commit(
    admin, fake_ea: FakeEA, monkeypatch: pytest.MonkeyPatch, session_factory, stash: FakeCache
) -> None:
    _client, user = admin
    await _seed(session_factory, access_left=0)
    credential_service._session.token, credential_service._session.expires_at = "old", 2**31
    original = AsyncSession.commit
    blocked = asyncio.Event()

    async def stuck_commit(self: AsyncSession) -> None:
        blocked.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(AsyncSession, "commit", stuck_commit)
    task = credential_service._detach(
        credential_service._store_admin_grant(session_factory, _admin_req(user), _admin_grant())
    )
    await blocked.wait()
    await credential_service.drain(timeout=0.01)
    assert credential_service._UNSAVED_KEY in stash.store

    # 停机：任务被取消、内存清空，重启后从 Redis 补写，连同审计和更新人
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    monkeypatch.setattr(AsyncSession, "commit", original)
    monkeypatch.setattr(credential_service, "_unsaved", {})
    # 补写后管理员换到的 access token 还有效，直接用，不再找 EA 换
    assert await credential_service.get_access_token(session_factory) == "admin-access"
    assert fake_ea.calls == []
    row = await _row(session_factory)
    assert row is not None
    assert row.updated_by == user.id
    assert get_cipher().decrypt(row.encrypted_client_secret) == "new-secret"
    logs = await _audits(session_factory)
    assert len(logs) == 1 and logs[0].payload["write_id"] == "w-1"
    assert credential_service._session.token == ""
    assert stash.store == {}


async def test_recovered_admin_grant_ignores_generation_change(
    admin, monkeypatch: pytest.MonkeyPatch, session_factory, stash: FakeCache
) -> None:
    _client, user = admin
    await _seed(session_factory, access_left=0)
    failing = _fail_commits(monkeypatch)
    failing["left"] = 100
    with pytest.raises(OperationalError):
        await credential_service._store_admin_grant(
            session_factory, _admin_req(user), _admin_grant()
        )
    failing["left"] = 0
    # 写库失败期间后台刷新过一次（版本变了），管理员的新凭据仍然要生效
    async with session_factory() as db:
        row = await credential_service._lock_row(db)
        row.generation = 5
        await db.commit()
    async with session_factory() as db:
        row = await credential_service._lock_row(db)
        assert await credential_service._recover_unsaved(db, row)
    row = await _row(session_factory)
    assert row is not None
    assert get_cipher().decrypt(row.encrypted_refresh_token) == "admin-rotated"
    assert row.updated_by == user.id
    assert len(await _audits(session_factory)) == 1


async def test_older_admin_grant_does_not_override_newer_save(
    admin, monkeypatch: pytest.MonkeyPatch, session_factory, stash: FakeCache
) -> None:
    _client, user = admin
    await _seed(session_factory, access_left=0)
    failing = _fail_commits(monkeypatch)
    failing["left"] = 100
    with pytest.raises(OperationalError):
        await credential_service._store_admin_grant(
            session_factory, _admin_req(user, "old"), _admin_grant("admin-old")
        )
    # 第一份一直没写进去；随后又保存了一次，这次成功
    failing["left"] = 0
    await credential_service._store_admin_grant(
        session_factory, _admin_req(user, "new"), _admin_grant("admin-new")
    )
    async with session_factory() as db:
        row = await credential_service._lock_row(db)
        assert not await credential_service._recover_unsaved(db, row)
    row = await _row(session_factory)
    assert row is not None
    assert get_cipher().decrypt(row.encrypted_refresh_token) == "admin-new"
    assert [log.payload["write_id"] for log in await _audits(session_factory)] == ["new"]
    assert stash.store == {}


async def test_admin_save_order_does_not_depend_on_clock(
    admin, monkeypatch: pytest.MonkeyPatch, session_factory, stash: FakeCache
) -> None:
    _client, user = admin
    await _seed(session_factory, access_left=0)
    clock = {"now": 200.0}
    monkeypatch.setattr(credential_service.time, "time", lambda: clock["now"])
    # 一份更早的保存一直没写进库，它所在进程的时钟偏快
    stale = credential_service._Unsaved(
        _admin_grant("stale-token"), 0, 300.0, "new-secret", _admin_req(user, "stale").admin
    )
    await credential_service._remember(stale)
    await credential_service._store_admin_grant(
        session_factory, _admin_req(user, "old"), _admin_grant("old-token")
    )
    # 之后的保存落在时钟偏慢的进程上，照样生效
    clock["now"] = 100.0
    await credential_service._store_admin_grant(
        session_factory, _admin_req(user, "new", after_audit=1), _admin_grant("new-token")
    )
    async with session_factory() as db:
        row = await credential_service._lock_row(db)
        assert not await credential_service._recover_unsaved(db, row)
    row = await _row(session_factory)
    assert row is not None
    assert get_cipher().decrypt(row.encrypted_refresh_token) == "new-token"
    assert [log.payload["write_id"] for log in await _audits(session_factory)] == ["old", "new"]
    assert stash.store == {}


async def test_first_save_commit_failure_is_recovered(
    admin, fake_ea: FakeEA, monkeypatch: pytest.MonkeyPatch, session_factory, stash: FakeCache
) -> None:
    _client, user = admin
    failing = _fail_commits(monkeypatch)
    failing["left"] = 100
    with pytest.raises(OperationalError):
        await credential_service._store_admin_grant(
            session_factory, _admin_req(user), _admin_grant()
        )
    assert await _row(session_factory) is None
    # 重启：只剩 Redis 里那份，数据库里还没有凭据行
    failing["left"] = 0
    monkeypatch.setattr(credential_service, "_unsaved", {})
    assert await credential_service.get_access_token(session_factory) == "admin-access"
    assert fake_ea.calls == []
    row = await _row(session_factory)
    assert row is not None
    assert get_cipher().decrypt(row.encrypted_refresh_token) == "admin-rotated"
    assert row.updated_by == user.id
    assert len(await _audits(session_factory)) == 1
    assert stash.store == {}


async def test_first_recovery_racing_successful_save_uses_saved_row(
    admin, monkeypatch: pytest.MonkeyPatch, session_factory
) -> None:
    _client, user = admin
    req, grant = _admin_req(user), _admin_grant()
    # 第一次保存已换到 grant、还没写库，查询这时进入恢复流程
    await credential_service._remember(
        credential_service._Unsaved(grant, 0, time.time(), req.client_secret, req.admin)
    )
    original = credential_service._insert_placeholder
    raced = False

    async def insert_after_save(db: AsyncSession, secret: str, token: str) -> bool:
        nonlocal raced
        if not raced:
            raced = True
            # 恢复流程占位之前，原保存抢先写进库并清理了待补写记录
            await credential_service._store_admin_grant(session_factory, req, grant)
        return await original(db, secret, token)

    monkeypatch.setattr(credential_service, "_insert_placeholder", insert_after_save)
    assert await credential_service.get_access_token(session_factory) == "admin-access"
    assert len(await _audits(session_factory)) == 1


async def test_not_configured_without_pending_grant(session_factory) -> None:
    with pytest.raises(credential_service.Bf6NotConfiguredError):
        await credential_service.get_access_token(session_factory)
    assert await _row(session_factory) is None


async def test_overlong_user_id_is_upstream_error() -> None:
    response = httpx.Response(200, json={"playerStatsSummary": {"userId": "9" * 4301}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _r: response)) as http:
        with pytest.raises(bf6.Bf6Error):
            await resolver.lookup(http, "x", "EVT", None)


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
        httpx.Response(200, content=b'{"access_token": "a", "expires_in": 1e309}'),
        httpx.Response(200, json={"access_token": "a", "expires_in": True}),
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
        httpx.Response(200, content=b'{"playerStatsSummary": {"userId": 1e309}}'),
        httpx.Response(200, json={"playerStatsSummary": {"userId": 12.5}}),
        httpx.Response(200, json={"playerStatsSummary": {"userId": "99999999999999999999"}}),
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
