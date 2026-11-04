"""一键卡行动的任务编排：EA Gateway 与 Blaze 全部用假的"""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar

import pytest
import pytest_asyncio
from app.api.errors import EAApiError, ForbiddenError, ValidationError
from app.models import AuditLog, Base
from app.models.bf1 import Bf1CardJob
from app.services.bf1 import card_engine as engine
from app.services.bf1 import card_service
from app.services.bf1.card_service import CardService, OwnerCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.test_bf1_card_engine import OPS, RSP, details

OWNER = 1008847306560
ADMIN = 1005935009520
GAME_ID = 11473517750387
SERVER_ID = 12552064
CREDS = OwnerCredentials(remid="r", sid="s")


class FakeClient:
    """模拟一台服：states[0] 是开始前的状态，之后 getServerDetails 依次返回其余的，最后一个一直重复"""

    def __init__(
        self,
        states: list[dict],
        *,
        pid: int = OWNER,
        update_result: Any = None,
        apply_on_error: bool = False,
        admin_entry: dict | None = None,
    ):
        self.pid = pid
        self.check_login = True
        self.http_session = None
        self.remid, self.sid = "r", "s2"
        self.initial = states[0]
        self.states = list(states[1:]) or [states[0]]
        self.update_result = update_result if update_result is not None else {"result": "success"}
        # 返回错误但设置照样生效（banner 噪音的情形）
        self.apply_on_error = apply_on_error
        self.admin_entry = admin_entry or {"personaId": str(ADMIN), "displayName": "Admin-A"}
        self.rotation = RSP["mapRotations"][0]["maps"]
        self.updates: list[dict] = []
        self.chosen: list[tuple[str, int]] = []
        self.left = 0

    async def getFullServerDetails(self, game_id):  # noqa: N802
        return {
            "result": {
                "serverInfo": self.initial,
                "rspInfo": {
                    "server": {"serverId": str(SERVER_ID), "persistedGameId": "pgid"},
                    "owner": {"personaId": str(OWNER), "displayName": "M-KOISHI-M"},
                    "adminList": [self.admin_entry],
                },
            }
        }

    async def RSPgetServerDetails(self, server_id):  # noqa: N802
        return {
            "result": {**RSP, "mapRotations": [{**RSP["mapRotations"][0], "maps": self.rotation}]}
        }

    async def updateServer(self, params):  # noqa: N802
        self.updates.append(params)
        if isinstance(self.update_result, dict) or self.apply_on_error:
            self.rotation = params["mapRotation"]["maps"]
        return self.update_result

    async def getServerDetails(self, game_id):  # noqa: N802
        st = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        return {"result": st}

    async def chooseLevel(self, guid, index):  # noqa: N802
        self.chosen.append((guid, index))
        return {"result": {}}

    async def leaveGame(self, game_id):  # noqa: N802
        self.left += 1
        return {"result": "success"}


class FakeBlaze:
    instances: ClassVar[list[FakeBlaze]] = []

    def __init__(self, persona_id, remid, sid):
        self.alive = False
        self.joins = 0
        FakeBlaze.instances.append(self)

    async def open(self):
        self.alive = True

    async def join(self, game_id):
        self.joins += 1

    async def close(self):
        self.alive = False


@pytest_asyncio.fixture
async def maker(tmp_path, monkeypatch):
    eng = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/card.db")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    mk = async_sessionmaker(eng, expire_on_commit=False)
    monkeypatch.setattr(card_service, "get_sessionmaker", lambda: mk)
    monkeypatch.setattr(card_service, "CardBlazeSession", FakeBlaze)

    async def _no_sleep(_s: float) -> None:
        await asyncio.sleep(0)

    monkeypatch.setattr(card_service, "SLEEP", _no_sleep)
    FakeBlaze.instances = []
    yield mk
    await card_service.shutdown_card_jobs()
    await eng.dispose()


def use_client(monkeypatch, client: FakeClient) -> None:
    async def _login(_creds):
        return client

    monkeypatch.setattr(card_service, "_login", _login)


async def wait_done(mk, job_id: int) -> Bf1CardJob:
    for _ in range(500):
        async with mk() as db:
            job = await db.get(Bf1CardJob, job_id)
            if job.status != "running" and job_id not in card_service._runners:
                return job
        await asyncio.sleep(0.01)
    raise AssertionError("任务没有结束")


EMPTY_CQ = details("Conquest", ["MP_Alps"] * 3)
OPS_STATE = details("BreakthroughLarge", OPS, soldiers=1)


async def test_card_hits_and_anchors(maker, monkeypatch):
    client = FakeClient([EMPTY_CQ, details("Conquest", ["MP_Amiens"] * 9, soldiers=1), OPS_STATE])
    use_client(monkeypatch, client)
    async with maker() as db:
        view, token = await CardService(db).start(CREDS, GAME_ID, "card", user=None, ip="1.2.3.4")
    assert view.status == "running" and token
    job = await wait_done(maker, view.id)

    assert job.status == "succeeded", job.events
    assert job.attempts == 2
    assert job.result_maps == OPS
    # 种子 1 次 + 第 1 轮 1 次 + 未中重置 2 次 + 第 2 轮 1 次 + 锚定 1 次
    assert len(client.updates) == 6
    assert client.updates[0]["mapRotation"]["maps"] == engine.seed_maps(64)
    assert client.updates[-1]["mapRotation"]["maps"] == engine.anchor_maps(OPS)
    assert client.updates[-1]["serverSettings"]["password"] == "123"
    assert len(client.chosen) == 2
    assert FakeBlaze.instances[0].joins == 2
    assert client.left == 2  # 未中离开 1 次 + 锚定后离开 1 次
    async with maker() as db:
        actions = list(await db.scalars(select(AuditLog.action).order_by(AuditLog.id)))
    assert actions == ["card_start", "card_success"]
    assert card_service.active_game_ids() == set()


async def test_admin_can_card(maker, monkeypatch):
    """服主之外，rspInfo.adminList 里的管理员也能用；任务记的是操作者本人"""
    client = FakeClient([details("BreakthroughLarge", OPS, soldiers=12)], pid=ADMIN)
    use_client(monkeypatch, client)
    async with maker() as db:
        pre = await CardService(db).precheck(CREDS, GAME_ID)
        assert (pre.is_owner, pre.is_admin) == (False, True)
        view, _ = await CardService(db).start(CREDS, GAME_ID, "anchor", user=None, ip=None)
    job = await wait_done(maker, view.id)
    assert job.status == "succeeded", job.events
    assert (job.persona_id, job.persona_name) == (ADMIN, "Admin-A")


async def test_admin_entry_uses_shared_member_parsing(maker, monkeypatch):
    """adminList 的 personaID / name 别名和服管身份识别同样认"""
    entry = {"personaID": str(ADMIN), "name": "Admin-B"}
    use_client(monkeypatch, FakeClient([EMPTY_CQ], pid=ADMIN, admin_entry=entry))
    async with maker() as db:
        pre = await CardService(db).precheck(CREDS, GAME_ID)
    assert pre.is_admin


async def test_bare_auth_error_is_verified_by_reading_back(maker, monkeypatch):
    """不带 updateServerBanner 的 ERR_AUTHORIZATION_REQUIRED：轮换真写进去了算成功，没写进去就失败"""
    busy = details("BreakthroughLarge", OPS, soldiers=12)
    noisy = FakeClient(
        [busy], pid=ADMIN, update_result="ERR_AUTHORIZATION_REQUIRED", apply_on_error=True
    )
    use_client(monkeypatch, noisy)
    async with maker() as db:
        view, _ = await CardService(db).start(CREDS, GAME_ID, "anchor", user=None, ip=None)
    job = await wait_done(maker, view.id)
    assert job.status == "succeeded", job.events
    assert noisy.rotation == engine.anchor_maps(OPS)

    denied = FakeClient([busy], pid=ADMIN, update_result="ERR_AUTHORIZATION_REQUIRED")
    use_client(monkeypatch, denied)
    async with maker() as db:
        view, token = await CardService(db).start(CREDS, GAME_ID, "anchor", user=None, ip=None)
    job = await wait_done(maker, view.id)
    assert job.status == "failed"
    assert "回读设置未生效" in job.message

    # 服务器停在别的轮换上、恢复同样被拒：报错，不标记已恢复
    denied.rotation = engine.anchor_maps(OPS)
    async with maker() as db:
        with pytest.raises(EAApiError, match="恢复失败"):
            await CardService(db).restore(view.id, token, None, CREDS)
    async with maker() as db:
        assert (await db.get(Bf1CardJob, view.id)).restored_at is None


async def test_start_requires_owner_and_empty_server(maker, monkeypatch):
    use_client(monkeypatch, FakeClient([EMPTY_CQ], pid=123))
    async with maker() as db:
        with pytest.raises(ForbiddenError, match="服主或管理员"):
            await CardService(db).start(CREDS, GAME_ID, "card", user=None, ip=None)

    use_client(monkeypatch, FakeClient([details("Conquest", ["MP_Alps"], soldiers=3)]))
    async with maker() as db:
        with pytest.raises(ValidationError, match="空服"):
            await CardService(db).start(CREDS, GAME_ID, "card", user=None, ip=None)

    use_client(monkeypatch, FakeClient([EMPTY_CQ]))
    async with maker() as db:
        with pytest.raises(ValidationError, match="不是 24 图行动"):
            await CardService(db).start(CREDS, GAME_ID, "anchor", user=None, ip=None)


async def test_permission_error_aborts_and_restore(maker, monkeypatch):
    client = FakeClient([EMPTY_CQ], update_result="无权限")
    use_client(monkeypatch, client)
    async with maker() as db:
        view, token = await CardService(db).start(CREDS, GAME_ID, "card", user=None, ip=None)
    job = await wait_done(maker, view.id)
    assert job.status == "failed"
    assert "无权限" in job.message

    async with maker() as db:
        with pytest.raises(ForbiddenError):
            await CardService(db).get(view.id, "wrong", None)
        got = await CardService(db).get(view.id, token, None)
        assert got.can_restore

    client.update_result = {"result": "success"}
    client.updates.clear()
    async with maker() as db:
        restored = await CardService(db).restore(view.id, token, None, CREDS)
    assert restored.restored_at is not None
    assert client.updates[0]["mapRotation"]["maps"] == RSP["mapRotations"][0]["maps"]
    assert client.updates[0]["mapRotation"]["mod"] == "63"


async def test_manual_anchor_skips_join_when_occupied(maker, monkeypatch):
    busy = details("BreakthroughLarge", OPS, soldiers=12)
    client = FakeClient([busy])
    use_client(monkeypatch, client)
    async with maker() as db:
        view, _ = await CardService(db).start(CREDS, GAME_ID, "anchor", user=None, ip=None)
    job = await wait_done(maker, view.id)
    assert job.status == "succeeded", job.events
    assert FakeBlaze.instances == []
    assert client.updates[-1]["mapRotation"]["maps"] == engine.anchor_maps(OPS)
    assert client.left == 0


async def test_cancel_and_one_job_per_server(maker, monkeypatch):
    client = FakeClient([EMPTY_CQ, details("Conquest", ["MP_Amiens"] * 9, soldiers=1)])
    use_client(monkeypatch, client)
    async with maker() as db:
        view, token = await CardService(db).start(CREDS, GAME_ID, "card", user=None, ip=None)
        with pytest.raises(ValidationError, match="已经有一个"):
            await CardService(db).start(CREDS, GAME_ID, "card", user=None, ip=None)
        await asyncio.sleep(0.05)
        cancelled = await CardService(db).cancel(view.id, token, None)
    assert cancelled.status == "cancelled"
    assert card_service.active_game_ids() == set()


async def test_mark_interrupted(maker):
    async with maker() as db:
        db.add(
            Bf1CardJob(
                kind="card",
                game_id=GAME_ID,
                server_id=SERVER_ID,
                persona_id=OWNER,
                token_hash="x",
                status="running",
                events=[],
            )
        )
        await db.commit()
    await card_service.mark_interrupted_jobs()
    async with maker() as db:
        job = await db.scalar(select(Bf1CardJob))
    assert job.status == "interrupted"


async def test_api_requires_credentials_and_token(client, test_session):
    res = await client.post("/api/v1/bf1/card/precheck", json={"game_id": GAME_ID})
    assert res.status_code == 400
    assert "remid" in res.json()["error"]["message"]

    res = await client.post(
        "/api/v1/bf1/card/precheck", json={"game_id": GAME_ID, "use_binding": True}
    )
    assert res.json()["error"]["message"] == "登录后才能使用绑定账号"

    test_session.add(
        Bf1CardJob(
            kind="card",
            game_id=GAME_ID,
            server_id=SERVER_ID,
            persona_id=OWNER,
            token_hash=card_service._hash("good"),
            status="failed",
            snapshot_enc="x",
            events=[],
        )
    )
    await test_session.commit()
    res = await client.get("/api/v1/bf1/card/jobs/1", headers={"X-Card-Token": "bad"})
    assert res.status_code == 403
    res = await client.get("/api/v1/bf1/card/jobs/1", headers={"X-Card-Token": "good"})
    assert res.status_code == 200
    assert res.json()["can_restore"] is True


# ----------------------------------------------------------------------------- 借号池账号

POOL_CREDS = OwnerCredentials(remid="r", sid="s", pool_persona_id=ADMIN)


@pytest.fixture
def pool_env(monkeypatch):
    """号池里有 ADMIN 和另一个号；记下让 Blaze 让号和走号池 client 的调用"""
    from app.services import ea_account_service

    state: dict[str, Any] = {"enabled": [ADMIN, 5], "released": [], "pool_clients": []}

    class _Accounts:
        def __init__(self, db):
            pass

        async def enabled_personas(self):
            return list(state["enabled"])

    async def _release(pid):
        state["released"].append(pid)

    monkeypatch.setattr(card_service, "EAAccountService", _Accounts)
    monkeypatch.setattr(card_service, "release_blaze_account", _release)
    yield state
    for pid in (ADMIN, 5):
        ea_account_service.release_persona(pid)


async def test_pool_account_is_reserved_while_card_runs(maker, monkeypatch, pool_env):
    from app.services.ea_account_service import reserved_personas

    client = FakeClient([details("BreakthroughLarge", OPS, soldiers=12)], pid=ADMIN)
    gate = asyncio.Event()
    orig_state = client.getServerDetails

    async def slow_state(game_id):
        await gate.wait()
        return await orig_state(game_id)

    client.getServerDetails = slow_state
    use_client(monkeypatch, client)
    async with maker() as db:
        view, _ = await CardService(db).start(POOL_CREDS, GAME_ID, "anchor", user=None, ip=None)
        # 生产 Blaze 先让出这个号，任务期间它被独占
        assert pool_env["released"] == [ADMIN]
        assert ADMIN in reserved_personas()
        # 同一个号不能同时借给另一台服
        with pytest.raises(ValidationError, match="正在给别的服卡行动"):
            await CardService(db).start(POOL_CREDS, GAME_ID + 1, "anchor", user=None, ip=None)
    gate.set()
    job = await wait_done(maker, view.id)
    assert job.status == "succeeded", job.events
    assert ADMIN not in reserved_personas()


async def test_pool_account_released_when_start_fails(maker, monkeypatch, pool_env):
    from app.services.ea_account_service import reserved_personas

    use_client(monkeypatch, FakeClient([details("Conquest", ["MP_Alps"], soldiers=3)], pid=ADMIN))
    async with maker() as db:
        with pytest.raises(ValidationError, match="空服"):
            await CardService(db).start(POOL_CREDS, GAME_ID, "card", user=None, ip=None)
    assert ADMIN not in reserved_personas()


async def test_pool_account_needs_another_account_left(maker, monkeypatch, pool_env):
    from app.services.ea_account_service import reserved_personas

    pool_env["enabled"] = [ADMIN]
    use_client(monkeypatch, FakeClient([EMPTY_CQ], pid=ADMIN))
    async with maker() as db:
        with pytest.raises(ValidationError, match="没有别的可用账号"):
            await CardService(db).start(POOL_CREDS, GAME_ID, "card", user=None, ip=None)
    assert pool_env["released"] == []
    assert ADMIN not in reserved_personas()


async def test_pool_precheck_and_restore_use_cached_pool_client(maker, monkeypatch, pool_env):
    """预检和恢复走号池 client（沿用登录态），不做完整登录"""
    from contextlib import asynccontextmanager

    client = FakeClient([EMPTY_CQ], pid=ADMIN, update_result="无权限")
    use_client(monkeypatch, client)

    @asynccontextmanager
    async def _pool_client(db, persona_id):
        pool_env["pool_clients"].append(persona_id)
        yield client

    async def _no_login(_creds):
        raise AssertionError("号池账号的预检和恢复不该完整登录")

    monkeypatch.setattr(card_service, "get_bf1_client_for_pool_account", _pool_client)
    async with maker() as db:
        view, token = await CardService(db).start(POOL_CREDS, GAME_ID, "card", user=None, ip=None)
    job = await wait_done(maker, view.id)
    assert job.status == "failed"

    monkeypatch.setattr(card_service, "_login", _no_login)
    client.update_result = {"result": "success"}
    async with maker() as db:
        pre = await CardService(db).precheck(POOL_CREDS, GAME_ID)
        assert pre.is_admin
        restored = await CardService(db).restore(view.id, token, None, POOL_CREDS)
    assert restored.restored_at is not None
    assert pool_env["pool_clients"] == [ADMIN, ADMIN]


async def test_resolve_pool_credentials_checks_site_role(maker, monkeypatch, pool_env):
    from types import SimpleNamespace

    from app.core.security import get_cipher
    from app.models import EAAccount

    roles: dict[str, Any] = {"ok": False}

    class _Authz:
        def __init__(self, db):
            pass

        async def require_role(self, **kw):
            assert kw["min_role"] == "admin"
            if not roles["ok"]:
                raise ForbiddenError("无权管理此服务器")

    candidates: list[int] = []

    async def _pool_admins(db, game_id, *, fresh=False):
        assert fresh
        return list(candidates)

    async def _admin_ids(db, game_id, *, fresh=False):
        return frozenset({ADMIN})

    monkeypatch.setattr(card_service, "ServerAuthzService", _Authz)
    monkeypatch.setattr(card_service, "pool_admin_personas", _pool_admins)
    monkeypatch.setattr(card_service, "server_admin_ids", _admin_ids)
    from app.services.ea_account_service import EAAccountService as RealAccounts

    monkeypatch.setattr(card_service, "EAAccountService", RealAccounts)
    user = SimpleNamespace(id=1)

    async with maker() as db:
        cipher = get_cipher()
        db.add(
            EAAccount(
                persona_id=ADMIN,
                encrypted_remid=cipher.encrypt("pool-remid"),
                encrypted_sid=cipher.encrypt("pool-sid"),
                enabled=True,
            )
        )
        await db.commit()

        with pytest.raises(ValidationError, match="登录后"):
            await card_service.resolve_pool_credentials(db, None, GAME_ID)
        with pytest.raises(ForbiddenError, match="借用平台账号需要"):
            await card_service.resolve_pool_credentials(db, user, GAME_ID)
        roles["ok"] = True
        with pytest.raises(ValidationError, match="都不是这台服的服主或管理员"):
            await card_service.resolve_pool_credentials(db, user, GAME_ID)
        from app.services import ea_account_service

        ea_account_service.reserve_persona(ADMIN)
        with pytest.raises(ValidationError, match="正在给别的服卡行动"):
            await card_service.resolve_pool_credentials(db, user, GAME_ID)
        ea_account_service.release_persona(ADMIN)
        candidates.append(ADMIN)
        creds = await card_service.resolve_pool_credentials(db, user, GAME_ID)
    assert (creds.remid, creds.sid, creds.pool_persona_id) == ("pool-remid", "pool-sid", ADMIN)
    assert "pool-remid" not in repr(creds)


async def test_pool_reservation_waits_for_in_flight_gateway_use(maker, monkeypatch, pool_env):
    from app.services.ea_account_service import gateway_using, reserved_personas

    use_client(monkeypatch, FakeClient([details("BreakthroughLarge", OPS, soldiers=12)], pid=ADMIN))
    order: list[str] = []
    orig_release = card_service.release_blaze_account

    async def release(pid):
        order.append("blaze-released")
        await orig_release(pid)

    monkeypatch.setattr(card_service, "release_blaze_account", release)

    async def in_flight():
        with gateway_using(ADMIN):
            await asyncio.sleep(0.3)
            order.append("gateway-done")

    holder = asyncio.create_task(in_flight())
    await asyncio.sleep(0)
    async with maker() as db:
        view, _ = await CardService(db).start(POOL_CREDS, GAME_ID, "anchor", user=None, ip=None)
    await holder
    assert order == ["gateway-done", "blaze-released"]
    await wait_done(maker, view.id)
    assert ADMIN not in reserved_personas()

    # 一直有请求拿着这个号：等不到就放弃借用
    monkeypatch.setattr(card_service, "RESERVE_WAIT_SECONDS", 0.2)
    with gateway_using(ADMIN):
        async with maker() as db:
            with pytest.raises(ValidationError, match="正在处理别的请求"):
                await CardService(db).start(POOL_CREDS, GAME_ID, "anchor", user=None, ip=None)
    assert ADMIN not in reserved_personas()


async def test_cancel_during_cleanup_still_releases_pool_account(maker, monkeypatch, pool_env):
    from app.services.ea_account_service import reserved_personas

    client = FakeClient([EMPTY_CQ], pid=ADMIN)
    use_client(monkeypatch, client)
    closing = asyncio.Event()
    never = asyncio.Event()

    class SlowCloseBlaze(FakeBlaze):
        async def close(self):
            closing.set()
            await never.wait()

    monkeypatch.setattr(card_service, "CardBlazeSession", SlowCloseBlaze)
    async with maker() as db:
        view, token = await CardService(db).start(POOL_CREDS, GAME_ID, "card", user=None, ip=None)
    runner = card_service._runners[view.id]
    await asyncio.sleep(0.05)

    async def stop():
        async with maker() as db:
            await CardService(db).cancel(view.id, token, None)

    first = asyncio.create_task(stop())
    await asyncio.wait_for(closing.wait(), 5)
    # 收尾卡在关 Blaze 时又点了一次停止：只取消一次，不会打断收尾
    second = asyncio.create_task(stop())
    await asyncio.sleep(0.05)
    assert runner.task.cancelling() == 1
    # 进程关闭时直接再取消：finally 里照样放掉账号和这台服
    runner.task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await runner.task
    await asyncio.gather(first, second)
    assert ADMIN not in reserved_personas()
    assert view.id not in card_service._runners
