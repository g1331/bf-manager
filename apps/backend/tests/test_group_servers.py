"""群组服务账号与绑服：两个条件、群成员的服务器权限、执行账号的选择、复核与服主视图

EA 一律打桩：服务器的服主 / 管理员名单（get_admin_identity）、remid 校验（verify_ea_cookie）、
服务账号的 client（get_bf1_client_for_group_account）。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest
from app.domain.ea.login.exceptions import EALoginError
from app.domain.games.bf1 import client_provider as cp
from app.models import AuditLog, GroupEaAccount, GroupServer, User
from app.services import group_server_service as gss
from app.services.auth_service import AuthService, EaIdentity
from app.services.bf1 import server_service as ss_module
from app.services.ea_login_finalizer import EALoginFinalizer
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from tests.test_accounts import _active_user, _login_cookie
from tests.test_groups import _invite, _join, _setup

API = "/api/v1"
GAME_ID = 777
SERVER_ID = 7001
SERVICE_PID = 5005
OWNER_PID = 2001  # 群主（_setup 里的 owner），EA 上是这台服的管理员
ALICE_PID = 2002  # 群里的管理员，EA 上什么都不是
BOB_PID = 2003  # 不在群里


class FakeClient:
    def __init__(self, ea: FakeEA, pid: int) -> None:
        self.ea = ea
        self.pid = pid
        self.access_token = None if pid in ea.broken else "token"

    async def getFullServerDetails(self, game_id: int) -> dict[str, Any]:  # noqa: N802
        admin = self.pid in self.ea.admins or self.pid == self.ea.owner
        rsp = {"server": {"serverId": str(SERVER_ID)}} if admin else {}
        return {"result": {"serverInfo": {"serverId": str(SERVER_ID)}, "rspInfo": rsp}}

    async def kickPlayer(self, game_id: int, persona_id: int, reason: str) -> dict[str, Any]:  # noqa: N802
        self.ea.kicked.append((self.pid, persona_id))
        return {"result": "ok"}


class FakeEA:
    def __init__(self) -> None:
        self.owner: int | None = 9999
        self.admins: set[int] = {OWNER_PID, SERVICE_PID}
        # 凭据失效的服务账号
        self.broken: set[int] = set()
        self.kicked: list[tuple[int, int]] = []


@pytest.fixture
def ea(monkeypatch) -> FakeEA:
    state = FakeEA()

    async def identity(self, game_id):
        return state.owner, sorted(state.admins), SERVER_ID, "测试服"

    async def verify(self, remid, sid):
        # remid 里带着 persona，方便造不同的服务账号
        pid = int(remid.rsplit("-", 1)[1])
        return EaIdentity(persona_id=pid, display_name=f"Svc{pid}", avatar_url=None)

    @asynccontextmanager
    async def group_client(db, account):
        yield FakeClient(state, account.persona_id)

    monkeypatch.setattr(ss_module.BF1ServerService, "get_admin_identity", identity)
    monkeypatch.setattr(AuthService, "verify_ea_cookie", verify)
    monkeypatch.setattr(cp, "get_bf1_client_for_group_account", group_client)
    monkeypatch.setattr(gss, "get_bf1_client_for_group_account", group_client)
    return state


async def _add_account(ac, gid: int, pid: int = SERVICE_PID):
    return await ac.post(
        f"{API}/groups/{gid}/accounts/cookie", json={"remid": f"remid-value-{pid}", "sid": "s"}
    )


async def _group_with_alice(env, db):
    ac, outbox, owner, alice, bob, gid = await _setup(env, db)
    token = await _invite(ac, gid)
    assert (await _join(ac, alice, token)).status_code == 200
    _login_cookie(ac, owner)
    return ac, outbox, owner, alice, bob, gid


async def _bind(ac, gid: int, **extra):
    return await ac.post(f"{API}/groups/{gid}/servers", json={"game_id": GAME_ID, **extra})


async def _my_role(ac, user) -> str | None:
    _login_cookie(ac, user)
    resp = await ac.get(f"{API}/bf1/server-admin/{GAME_ID}/my-role")
    assert resp.status_code == 200, resp.text
    return resp.json()["role"]


async def _load(db, user_id: int) -> User:
    return await db.scalar(
        select(User)
        .options(selectinload(User.ea_bindings))
        .where(User.id == user_id)
        .execution_options(populate_existing=True)
    )


async def test_bind_server_gives_group_members_admin(env, test_session, ea) -> None:
    ac, _, owner, alice, bob, gid = await _group_with_alice(env, test_session)

    resp = await _add_account(ac, gid)
    assert resp.status_code == 201, resp.text
    assert resp.json()["persona_id"] == SERVICE_PID and resp.json()["is_default"] is True
    stored = await test_session.scalar(select(GroupEaAccount))
    assert "remid-value" not in stored.encrypted_remid

    # 群里的管理员不能加账号、不能绑服
    _login_cookie(ac, alice)
    assert (await _add_account(ac, gid, 5006)).status_code == 403
    assert (await _bind(ac, gid)).status_code == 403

    _login_cookie(ac, owner)
    resp = await _bind(ac, gid)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "active" and body["bound_via"] == "admin"
    assert body["executor"]["persona_id"] == SERVICE_PID
    assert body["name"] == "测试服" and body["server_id"] == SERVER_ID

    # alice 在 EA 上什么都不是，经由群组成了这台服的管理员；bob 不在群里
    assert await _my_role(ac, alice) == "admin"
    assert await _my_role(ac, bob) is None
    # 群主自己在 EA 上就是管理员
    assert await _my_role(ac, owner) == "admin"

    _login_cookie(ac, alice)
    mine = (await ac.get(f"{API}/bf1/server-admin/mine")).json()["items"]
    assert [(i["server_id"], i["role"], i["via_group"]) for i in mine] == [
        (SERVER_ID, "admin", "测试 群")
    ]
    servers = (await ac.get(f"{API}/groups/{gid}/servers")).json()["items"]
    assert len(servers) == 1


async def test_bind_requires_binder_and_executor_to_manage_server(env, test_session, ea) -> None:
    ac, _, _owner, _, _, gid = await _group_with_alice(env, test_session)
    resp = await _bind(ac, gid)
    assert resp.json()["error"]["code"] == "GROUP_NO_ACCOUNT"

    assert (await _add_account(ac, gid)).status_code == 201
    # 绑定人不是服主或管理员
    ea.admins = {SERVICE_PID}
    resp = await _bind(ac, gid)
    assert resp.status_code == 403 and resp.json()["error"]["code"] == "GROUP_SERVER_NOT_YOURS"
    # 服务账号不是管理员
    ea.admins = {OWNER_PID}
    resp = await _bind(ac, gid)
    assert resp.json()["error"]["code"] == "GROUP_EXECUTOR_NOT_ADMIN"
    assert await test_session.scalar(select(GroupServer.id)) is None

    # 不指定账号时跳过不是管理员的默认账号，挑能用的
    ea.admins = {OWNER_PID, 5006}
    assert (await _add_account(ac, gid, 5006)).status_code == 201
    resp = await _bind(ac, gid)
    assert resp.status_code == 201 and resp.json()["executor"]["persona_id"] == 5006


async def test_kick_runs_with_group_account_and_audits_executor(env, test_session, ea) -> None:
    ac, _, _, alice, _, gid = await _group_with_alice(env, test_session)
    await _add_account(ac, gid)
    await _bind(ac, gid)

    _login_cookie(ac, alice)
    resp = await ac.post(f"{API}/bf1/server-admin/{GAME_ID}/kick", json={"persona_id": 42})
    assert resp.status_code == 200, resp.text
    assert ea.kicked == [(SERVICE_PID, 42)]
    log = await test_session.scalar(select(AuditLog).where(AuditLog.action == "kick_player"))
    assert log.user_id == alice.id and log.acting_persona_id == ALICE_PID
    assert log.executor_persona_id == SERVICE_PID
    assert log.payload["credential_source"] == "group_account"


async def test_provider_counts_login_failures_and_has_no_pool_fallback(
    env, test_session, ea
) -> None:
    ac, _, _, alice, bob, gid = await _group_with_alice(env, test_session)
    await _add_account(ac, gid)
    await _bind(ac, gid)
    ea.broken = {SERVICE_PID}

    user = await _load(test_session, alice.id)
    for _ in range(gss.ACCOUNT_FAILURE_LIMIT):
        provider = cp.GroupFirstBF1ClientProvider(test_session, user=user, game_id=GAME_ID)
        with pytest.raises(cp.ExecutorUnavailableError):
            async with provider.acquire():
                pass
    account = await test_session.scalar(select(GroupEaAccount))
    await test_session.refresh(account)
    assert account.status == "invalid" and account.failure_count == gss.ACCOUNT_FAILURE_LIMIT

    # 不在群里的人借不到群的账号
    outsider = await _load(test_session, bob.id)
    assert await gss.executor_accounts_for(test_session, outsider, game_id=GAME_ID) == []


async def test_pending_member_does_not_count(env, test_session, ea) -> None:
    ac, _, _, alice, _, gid = await _group_with_alice(env, test_session)
    await _add_account(ac, gid)
    await _bind(ac, gid)
    user = await _load(test_session, alice.id)
    user.status = "pending_binding"
    await test_session.commit()
    assert await gss.group_role_for_server(test_session, user, 1) is None
    assert await gss.executor_accounts_for(test_session, user, game_id=GAME_ID) == []


async def test_daily_recheck_revokes_and_notifies_owner(env, test_session, ea) -> None:
    ac, outbox, _, alice, _, gid = await _group_with_alice(env, test_session)
    await _add_account(ac, gid)
    await _bind(ac, gid)
    sent = len(outbox.outbox)

    # 服务账号被撤了管理员：标出问题，但权限还在
    ea.admins = {OWNER_PID}
    await gss.recheck_all(test_session)
    gs = await test_session.scalar(select(GroupServer))
    await test_session.refresh(gs)
    assert gs.status == "active" and gs.executor_problem == gss.PROBLEM_EXECUTOR_NOT_ADMIN
    assert await _my_role(ac, alice) == "admin"
    mails = outbox.outbox[sent:]
    assert [m.to for m in mails] == ["owner@example.com"]
    assert mails[0].kind == "group_problems" and "测试服" in mails[0].text

    # 同样的问题第二天不再重复发信
    await gss.recheck_all(test_session)
    assert len(outbox.outbox) == sent + 1

    # 绑定人自己也被撤了：这台服在群里失效，群成员没权限了
    ea.admins = set()
    await gss.recheck_all(test_session)
    await test_session.refresh(gs)
    assert gs.status == "revoked" and gs.status_reason == gss.REASON_BINDER_LOST
    assert await _my_role(ac, alice) is None
    assert len(outbox.outbox) == sent + 2

    # 绑定人恢复管理员后复核自动恢复
    ea.admins = {OWNER_PID, SERVICE_PID}
    await gss.recheck_all(test_session)
    await test_session.refresh(gs)
    assert gs.status == "active" and gs.executor_problem is None


async def test_server_owner_sees_and_removes_groups(env, test_session, ea) -> None:
    ac, _, _, alice, bob, gid = await _group_with_alice(env, test_session)
    await _add_account(ac, gid)
    await _bind(ac, gid)
    ea.owner = BOB_PID

    # 群里的管理员在这台服上只是 admin，看不到服主视图
    _login_cookie(ac, alice)
    assert (await ac.get(f"{API}/bf1/server-admin/{GAME_ID}/groups")).status_code == 403

    _login_cookie(ac, bob)
    items = (await ac.get(f"{API}/bf1/server-admin/{GAME_ID}/groups")).json()["items"]
    assert [(i["group_name"], i["bound_via"], i["status"]) for i in items] == [
        ("测试 群", "admin", "active")
    ]
    resp = await ac.delete(f"{API}/bf1/server-admin/{GAME_ID}/groups/{gid}")
    assert resp.status_code == 204
    assert await test_session.scalar(select(GroupServer.id)) is None
    log = await test_session.scalar(
        select(AuditLog).where(AuditLog.action == "group_server_removed_by_owner")
    )
    assert log.group_id == gid and log.user_id == bob.id
    assert await _my_role(ac, alice) is None


async def test_remove_account_leaves_server_without_executor(env, test_session, ea) -> None:
    ac, _, _, _, _, gid = await _group_with_alice(env, test_session)
    account_id = (await _add_account(ac, gid)).json()["id"]
    await _bind(ac, gid)
    assert (await ac.delete(f"{API}/groups/{gid}/accounts/{account_id}")).status_code == 204
    item = (await ac.get(f"{API}/groups/{gid}/servers")).json()["items"][0]
    assert item["executor"] is None and item["executor_problem"] == gss.PROBLEM_NO_EXECUTOR
    assert item["status"] == "active"


async def test_ea_password_login_saves_group_account_for_owner_only(env, test_session, ea) -> None:
    _, _, owner, alice, _, gid = await _group_with_alice(env, test_session)
    finalizer = EALoginFinalizer()
    result = await finalizer._save_group_account(
        test_session,
        owner.id,
        gid,
        persona_id=6006,
        display_name="Pw",
        avatar_url=None,
        remid="r",
        sid="s",
        session="sess",
    )
    account = await test_session.get(GroupEaAccount, result.account_id)
    assert account is not None and account.group_id == gid and account.persona_id == 6006

    with pytest.raises(EALoginError):
        await finalizer._save_group_account(
            test_session,
            alice.id,
            gid,
            persona_id=6007,
            display_name=None,
            avatar_url=None,
            remid="r",
            sid="s",
            session=None,
        )


async def test_non_member_gets_404_on_group_server_routes(env, test_session, ea) -> None:
    ac, _, _, _, bob, gid = await _group_with_alice(env, test_session)
    other = await _active_user(test_session, user_id=29, email="x@example.com", persona_id=2009)
    for user in (bob, other):
        _login_cookie(ac, user)
        assert (await ac.get(f"{API}/groups/{gid}/servers")).status_code == 404
        assert (await ac.get(f"{API}/groups/{gid}/accounts")).status_code == 404
