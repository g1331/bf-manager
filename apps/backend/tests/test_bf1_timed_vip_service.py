"""计时 VIP 服务：加 V / 下 V / checkvip 与到期自动下 V

用一个有状态的假 EA（VIP 名单随 add / remove 变化）驱动 TimedVipService 与后台 _tick，
锁定这些行为：
- 普通服随加随生效，到期由后台用授予人的绑定凭据下掉；
- 行动服单条操作只改记录，checkvip 在有人时先删过期再补空位，空服时拒绝；
- 对账：别人在 EA 侧下了 / 加了 V，记录跟着变。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from app.api.errors import AppError, EAApiError
from app.domain.games.bf1.client_provider import ExecutorUnavailableError
from app.models import AuditLog, Server, ServerMembership
from app.models.bf1 import Bf1GameInstance, Bf1ServerVip
from app.services.bf1 import timed_vip_service as svc
from app.services.bf1.timed_vip_service import TimedVipService
from sqlalchemy import select

GAME_ID = 7013912860192
RSP_SERVER_ID = 12478776
IMG = "[BB_PREFIX]/gamedata/Tunguska/34/1/{}_LandscapeLarge-xxx.jpg"


class FakeEA:
    """一台服的 EA 侧状态，所有凭据共享。"""

    def __init__(
        self,
        *,
        mode: str = "Conquest",
        map_name: str = "MP_Amiens",
        rotation: tuple[str, ...] = ("MP_Amiens", "MP_Scar"),
        soldiers: int = 20,
        vips: dict[int, str] | None = None,
    ) -> None:
        self.mode = mode
        self.map_name = map_name
        self.rotation = list(rotation)
        self.soldiers = soldiers
        self.vips: dict[int, str] = dict(vips or {})
        self.calls: list[tuple] = []
        self.fail: dict[str, str] = {}

    def detail(self) -> dict:
        return {
            "result": {
                "serverInfo": {
                    "name": "测试服",
                    "mapMode": self.mode,
                    "mapName": self.map_name,
                    "guid": "guid-1",
                    "rotation": [{"mapImage": IMG.format(m)} for m in self.rotation],
                    "slots": {"Soldier": {"current": self.soldiers, "max": 64}},
                },
                "rspInfo": {
                    "server": {"serverId": str(RSP_SERVER_ID)},
                    "vipList": [
                        {"personaId": str(p), "displayName": n} for p, n in self.vips.items()
                    ],
                },
            }
        }


class FakeClient:
    def __init__(self, ea: FakeEA) -> None:
        self.ea = ea

    async def getFullServerDetails(self, gameId):  # noqa: N802, N803
        return self.ea.detail()

    async def addServerVip(self, personaId, serverId):  # noqa: N802, N803
        self.ea.calls.append(("add", personaId, serverId))
        if "add" in self.ea.fail:
            return self.ea.fail["add"]
        if personaId in self.ea.vips:
            return "玩家已经是VIP了"
        self.ea.vips[personaId] = f"P{personaId}"
        return {"env": {}}

    async def removeServerVip(self, personaId, serverId):  # noqa: N802, N803
        self.ea.calls.append(("remove", personaId, serverId))
        if "remove" in self.ea.fail:
            return self.ea.fail["remove"]
        self.ea.vips.pop(personaId, None)
        return {"env": {}}

    async def chooseLevel(self, persistedGameId, levelIndex):  # noqa: N802, N803
        self.ea.calls.append(("choose", persistedGameId, levelIndex))
        return {"env": {}}


class FakeProvider:
    credential_source = "binding"

    def __init__(self, ea: FakeEA) -> None:
        self.ea = ea

    @asynccontextmanager
    async def acquire(self):
        yield FakeClient(self.ea)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(svc, "EA_WRITE_INTERVAL", 0)


def _service(db, user, ea: FakeEA) -> TimedVipService:
    return TimedVipService(db, user=user, game_id=GAME_ID, client_provider=FakeProvider(ea))


async def _rows(db) -> dict[int, Bf1ServerVip]:
    return {r.persona_id: r for r in await db.scalars(select(Bf1ServerVip))}


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


# ----------------------------------------------------------------------------- 普通服


async def test_normal_server_grant_adds_immediately_and_renews(admin_client, test_session):
    _, admin = admin_client
    ea = FakeEA()
    service = _service(test_session, admin, ea)

    msg = await service.grant(111, 3, display_name="Alice")
    assert ea.calls == [("add", 111, RSP_SERVER_ID)]
    assert "到期" in msg
    row = (await _rows(test_session))[111]
    assert row.status == "active" and row.granted_by_user_id == admin.id
    first = _aware(row.expires_at)
    assert timedelta(days=2, hours=23) < first - datetime.now(UTC) <= timedelta(days=3)

    await service.grant(111, 2)
    # 续期只改记录，不再调 EA
    assert len(ea.calls) == 1
    assert _aware((await _rows(test_session))[111].expires_at) == first + timedelta(days=2)

    audit = list(await test_session.scalars(select(AuditLog).where(AuditLog.action == "add_vip")))
    assert len(audit) == 2 and audit[0].payload["status"] == "active"


async def test_permanent_vip_needs_confirmation(admin_client, test_session):
    _, admin = admin_client
    ea = FakeEA(vips={222: "Bob"})
    service = _service(test_session, admin, ea)

    with pytest.raises(AppError) as e:
        await service.grant(222, 7)
    assert e.value.code == "VIP_IS_PERMANENT" and e.value.status_code == 409

    await service.grant(222, 7, allow_permanent_to_timed=True)
    assert (await _rows(test_session))[222].status == "active"
    assert ea.calls == []


async def test_normal_server_revoke_and_external_removal(admin_client, test_session):
    _, admin = admin_client
    ea = FakeEA()
    service = _service(test_session, admin, ea)
    await service.grant(111, 3)
    await service.grant(333, 3)

    await service.revoke(111)
    assert ("remove", 111, RSP_SERVER_ID) in ea.calls
    # 333 被别的机器人在 EA 侧下掉，下次查看时记录跟着删
    ea.vips.pop(333)
    view = await service.view()
    assert view.items == [] and await _rows(test_session) == {}


async def test_ea_failure_leaves_records_untouched(admin_client, test_session):
    _, admin = admin_client
    ea = FakeEA()
    ea.fail["add"] = "服务器VIP位已满"
    with pytest.raises(EAApiError):
        await _service(test_session, admin, ea).grant(111, 3)
    assert await _rows(test_session) == {}
    failed = await test_session.scalar(select(AuditLog).where(AuditLog.result == "failure"))
    assert failed is not None and failed.action == "add_vip"


# ----------------------------------------------------------------------------- 行动服


def _operation_ea(**kw) -> FakeEA:
    return FakeEA(
        mode="BreakthroughLarge",
        map_name="MP_Scar",
        rotation=("MP_Volga", "MP_Scar", "MP_Amiens"),
        **kw,
    )


async def test_operation_grant_and_revoke_only_touch_records(admin_client, test_session):
    _, admin = admin_client
    ea = _operation_ea(vips={500: "Perm"})
    service = _service(test_session, admin, ea)

    msg = await service.grant(111, 7, display_name="Alice")
    assert "待生效" in msg
    await service.grant(111, 3)
    await service.revoke(500)
    assert ea.calls == []

    rows = await _rows(test_session)
    assert rows[111].status == "pending" and rows[111].remaining_seconds == 10 * 86400
    assert rows[111].display_name == "Alice"
    # 永久 VIP 下 V：标记为到期，等 checkvip
    assert rows[500].status == "active"
    assert _aware(rows[500].expires_at) <= datetime.now(UTC)

    view = await service.view()
    assert view.operation and view.campaign_start  # 圣康坦的伤痕是战役第一张
    assert {i.persona_id: i.queue_position for i in view.items} == {111: 1, 500: None}


async def test_checkvip_removes_expired_then_fills_slots_and_restarts(admin_client, test_session):
    _, admin = admin_client
    full = {1000 + i: f"V{i}" for i in range(49)}
    ea = _operation_ea(vips={**full, 500: "Old"})
    service = _service(test_session, admin, ea)
    await service.revoke(500)  # 50 人满，500 标记到期
    await service.grant(111, 7)
    await service.grant(222, None)

    result = await service.apply(restart=True)

    assert [c for c in ea.calls if c[0] == "remove"] == [("remove", 500, RSP_SERVER_ID)]
    # 只空出一个位：先排队的 111 补上，222 继续排队
    assert [c for c in ea.calls if c[0] == "add"] == [("add", 111, RSP_SERVER_ID)]
    assert ("choose", "guid-1", 1) in ea.calls
    assert (result.removed, result.added, result.waiting, result.restarted) == (1, 1, 1, True)

    rows = await _rows(test_session)
    assert rows[111].status == "active"
    expires = _aware(rows[111].expires_at) - datetime.now(UTC)
    assert timedelta(days=6, hours=23) < expires <= timedelta(days=7)
    assert rows[222].status == "pending" and 500 not in rows

    actions = {a.action for a in await test_session.scalars(select(AuditLog))}
    assert {"vip_apply", "choose_level"} <= actions


async def test_checkvip_refuses_on_empty_operation_server(admin_client, test_session):
    _, admin = admin_client
    ea = _operation_ea(soldiers=0)
    service = _service(test_session, admin, ea)
    await service.grant(111, 7)

    with pytest.raises(AppError) as e:
        await service.apply(restart=False)
    assert e.value.code == "VIP_SERVER_EMPTY"
    assert ea.calls == []


async def test_queued_vip_added_externally_starts_clock(admin_client, test_session):
    _, admin = admin_client
    ea = _operation_ea()
    service = _service(test_session, admin, ea)
    await service.grant(111, 2)
    ea.vips[111] = "Alice"  # 别的管理员手动加上了

    await service.view()
    row = (await _rows(test_session))[111]
    assert row.status == "active" and row.remaining_seconds is None


# ----------------------------------------------------------------------------- 到期自动下 V


async def _seed_expired(db, admin, ea: FakeEA, *, game_id: int = GAME_ID) -> Server:
    await _service(db, admin, ea).grant(111, 1)
    row = (await _rows(db))[111]
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    server = await db.scalar(select(Server))
    now = datetime.now(UTC)
    db.add(
        Bf1GameInstance(
            game_id=game_id, server_id=RSP_SERVER_ID, name="测试服", first_seen=now, last_seen=now
        )
    )
    await db.commit()
    return server


def _patch_tick(
    monkeypatch,
    ea: FakeEA,
    *,
    mode: str = "Conquest",
    usable: set[int] | None = None,
    demoted: set[int] | None = None,
):
    """usable：哪些人拿得到能用的凭据（None 表示都能）；demoted：哪些人已经没有本服管理权限"""

    async def states(db, game_ids):
        return {g: {"mode": mode, "map": ea.map_name} for g in game_ids}

    tried: list[int] = []

    class Provider:
        def __init__(self, db, *, user, game_id, server_pk=None, pool_fallback=False):
            assert pool_fallback is False
            assert server_pk is not None
            self.user = user
            self.credential_source = "group_account"
            self.executor_persona_id = 4242

        @asynccontextmanager
        async def acquire(self):
            tried.append(self.user.id)
            if usable is not None and self.user.id not in usable:
                raise ExecutorUnavailableError()
            yield FakeClient(ea)

    class Authz:
        def __init__(self, db):
            pass

        async def resolve_role(self, *, user, game, server_id):
            return (None if demoted and user.id in demoted else "admin"), False

    monkeypatch.setattr(svc, "get_operation_states", states)
    monkeypatch.setattr(svc, "GroupFirstBF1ClientProvider", Provider)
    monkeypatch.setattr(svc, "ServerAuthzService", Authz)
    return tried


async def test_tick_removes_expired_vip_with_granter_credentials(
    admin_client, test_session, monkeypatch
):
    _, admin = admin_client
    ea = FakeEA()
    await _seed_expired(test_session, admin, ea)
    tried = _patch_tick(monkeypatch, ea)

    await svc._tick(test_session)

    assert ("remove", 111, RSP_SERVER_ID) in ea.calls and 111 not in ea.vips
    assert tried == [admin.id]
    assert await _rows(test_session) == {}
    log = await test_session.scalar(select(AuditLog).where(AuditLog.action == "vip_expire"))
    assert log is not None and log.user_id is None and log.payload["executor_user_id"] == admin.id
    assert log.payload["credential_source"] == "group_account"
    assert log.executor_persona_id == 4242


async def test_tick_skips_operation_servers(admin_client, test_session, monkeypatch):
    _, admin = admin_client
    ea = FakeEA()
    await _seed_expired(test_session, admin, ea)
    tried = _patch_tick(monkeypatch, ea, mode="BreakthroughLarge")

    await svc._tick(test_session)

    assert tried == [] and 111 in ea.vips
    assert (await _rows(test_session))[111].attempts == 0


async def test_tick_falls_back_to_other_admins_then_records_error(
    admin_client, user_client, test_session, monkeypatch
):
    _, admin = admin_client
    _, other = user_client
    ea = FakeEA()
    server = await _seed_expired(test_session, admin, ea)
    test_session.add(ServerMembership(user_id=other.id, server_pk=server.id, role="admin"))
    await test_session.commit()

    tried = _patch_tick(monkeypatch, ea, usable={other.id})
    await svc._tick(test_session)
    assert tried == [admin.id, other.id] and 111 not in ea.vips


async def test_tick_skips_candidates_without_current_permission(
    admin_client, user_client, test_session, monkeypatch
):
    """授予人已经没有本服管理权限（退群、服被移出群）：不用他的身份，换下一个"""
    _, admin = admin_client
    _, other = user_client
    ea = FakeEA()
    server = await _seed_expired(test_session, admin, ea)
    test_session.add(ServerMembership(user_id=other.id, server_pk=server.id, role="admin"))
    await test_session.commit()

    tried = _patch_tick(monkeypatch, ea, demoted={admin.id})
    await svc._tick(test_session)
    assert tried == [other.id] and 111 not in ea.vips


async def test_tick_without_usable_credentials_backs_off(admin_client, test_session, monkeypatch):
    _, admin = admin_client
    ea = FakeEA()
    await _seed_expired(test_session, admin, ea)
    tried = _patch_tick(monkeypatch, ea, usable=set())

    await svc._tick(test_session)
    row = (await _rows(test_session))[111]
    assert row.attempts == 1 and "没法自动下 V" in (row.last_error or "")

    # 退避期内不再重试
    await svc._tick(test_session)
    assert tried == [admin.id]
