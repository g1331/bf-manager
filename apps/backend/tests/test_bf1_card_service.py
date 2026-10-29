"""一键卡行动的任务编排：EA Gateway 与 Blaze 全部用假的"""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar

import pytest
import pytest_asyncio
from app.api.errors import ForbiddenError, ValidationError
from app.models import AuditLog, Base
from app.models.bf1 import Bf1CardJob
from app.services.bf1 import card_engine as engine
from app.services.bf1 import card_service
from app.services.bf1.card_service import CardService, OwnerCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.test_bf1_card_engine import OPS, RSP, details

OWNER = 1008847306560
GAME_ID = 11473517750387
SERVER_ID = 12552064
CREDS = OwnerCredentials(remid="r", sid="s")


class FakeClient:
    """模拟一台服：states[0] 是开始前的状态，之后 getServerDetails 依次返回其余的，最后一个一直重复"""

    def __init__(self, states: list[dict], *, pid: int = OWNER, update_result: Any = None):
        self.pid = pid
        self.check_login = True
        self.http_session = None
        self.remid, self.sid = "r", "s2"
        self.initial = states[0]
        self.states = list(states[1:]) or [states[0]]
        self.update_result = update_result if update_result is not None else {"result": "success"}
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
                },
            }
        }

    async def RSPgetServerDetails(self, server_id):  # noqa: N802
        return {
            "result": {**RSP, "mapRotations": [{**RSP["mapRotations"][0], "maps": self.rotation}]}
        }

    async def updateServer(self, params):  # noqa: N802
        self.updates.append(params)
        if isinstance(self.update_result, dict):
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


async def test_start_requires_owner_and_empty_server(maker, monkeypatch):
    use_client(monkeypatch, FakeClient([EMPTY_CQ], pid=123))
    async with maker() as db:
        with pytest.raises(ForbiddenError):
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
