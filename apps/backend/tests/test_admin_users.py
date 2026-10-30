"""后台用户管理：列表、冻结、解冻，冻结后会话、API Key、群组挂服、服务器权限一并失效"""

from __future__ import annotations

from app.domain.games.bf1 import client_provider as cp
from app.models import AuditLog, GroupServer, User
from app.services import api_key_service
from app.services.api_key_service import ApiKeyService
from app.services.authz_service import ServerAuthzService
from app.services.group_server_service import REASON_BINDER_FROZEN, recheck_all
from sqlalchemy import select

from tests.test_accounts import _active_user, _login_cookie
from tests.test_group_servers import (  # noqa: F401  ea 是 fixture
    GAME_ID,
    _add_account,
    _bind,
    _group_with_alice,
    _load,
    _my_role,
    ea,
)

API = "/api/v1"


async def _admin(db) -> User:
    admin = await _active_user(db, user_id=90, email="root@example.com", persona_id=9090)
    admin.role = "admin"
    await db.commit()
    return admin


async def test_list_and_search_users(env, test_session) -> None:
    ac, _, _ = env
    admin = await _admin(test_session)
    await _active_user(test_session, user_id=31, email="carol@example.com", persona_id=3131)
    await _active_user(test_session, user_id=32, email="dave@example.com", persona_id=3232)

    _login_cookie(ac, admin)
    body = (await ac.get(f"{API}/admin/users")).json()
    assert body["total"] == 3 and [i["id"] for i in body["items"]] == [90, 32, 31]
    assert (await ac.get(f"{API}/admin/users", params={"q": "carol"})).json()["total"] == 1
    hit = (await ac.get(f"{API}/admin/users", params={"q": "3232"})).json()["items"]
    assert [i["id"] for i in hit] == [32]
    admins = (await ac.get(f"{API}/admin/users", params={"only": "admin"})).json()["items"]
    assert [i["id"] for i in admins] == [90]

    # 普通用户进不来
    carol = await test_session.get(User, 31)
    _login_cookie(ac, carol)
    assert (await ac.get(f"{API}/admin/users")).status_code == 403


async def test_freeze_logs_out_revokes_keys_and_audits(env, test_session) -> None:
    ac, _, _ = env
    admin = await _admin(test_session)
    carol = await _active_user(test_session, user_id=31, email="carol@example.com", persona_id=3131)
    _, raw = await ApiKeyService(test_session).create(carol, "bot")
    assert await api_key_service.resolve(test_session, raw) is not None

    _login_cookie(ac, carol)
    assert (await ac.get(f"{API}/me/ea-bindings")).status_code == 200
    carol_cookie = ac.cookies.get("bfm_access_token")

    _login_cookie(ac, admin)
    resp = await ac.post(f"{API}/admin/users/31/freeze", json={"reason": "  刷接口  "})
    assert resp.status_code == 200, resp.text
    item = resp.json()
    assert item["is_frozen"] and item["frozen_reason"] == "刷接口"
    assert item["active_api_keys"] == 0 and item["frozen_by_name"]

    # 会话、Key 都失效
    ac.cookies.set("bfm_access_token", carol_cookie)
    assert (await ac.get(f"{API}/me/ea-bindings")).status_code == 401
    assert await api_key_service.resolve(test_session, raw) is None

    log = await test_session.scalar(select(AuditLog).where(AuditLog.action == "user_freeze"))
    assert log.user_id == admin.id and log.game == "site" and log.target_persona_id == 3131
    assert log.payload["reason"] == "刷接口" and log.payload["revoked_keys"] == 1

    # 解冻：能重新登录，吊销的 Key 不恢复，旧会话也不复活
    _login_cookie(ac, admin)
    resp = await ac.post(f"{API}/admin/users/31/unfreeze")
    assert resp.status_code == 200 and resp.json()["is_frozen"] is False
    assert resp.json()["frozen_reason"] is None
    ac.cookies.set("bfm_access_token", carol_cookie)
    assert (await ac.get(f"{API}/me/ea-bindings")).status_code == 401
    carol = await _load(test_session, 31)
    _login_cookie(ac, carol)
    assert (await ac.get(f"{API}/me/ea-bindings")).status_code == 200
    assert await api_key_service.resolve(test_session, raw) is None
    assert await test_session.scalar(select(AuditLog.id).where(AuditLog.action == "user_unfreeze"))


async def test_cannot_freeze_self_or_admin(env, test_session) -> None:
    ac, _, _ = env
    admin = await _admin(test_session)
    other = await _active_user(test_session, user_id=91, email="r2@example.com", persona_id=9191)
    other.role = "admin"
    await test_session.commit()
    _login_cookie(ac, admin)
    for uid, code in ((90, "USER_FREEZE_SELF"), (91, "USER_FREEZE_ADMIN")):
        resp = await ac.post(f"{API}/admin/users/{uid}/freeze", json={"reason": "x"})
        assert resp.status_code == 409 and resp.json()["error"]["code"] == code
    resp = await ac.post(f"{API}/admin/users/404/freeze", json={"reason": "x"})
    assert resp.status_code == 404


async def test_freezing_binder_revokes_group_server(env, test_session, ea) -> None:  # noqa: F811
    ac, _, owner, alice, _, gid = await _group_with_alice(env, test_session)
    await _add_account(ac, gid)
    await _bind(ac, gid)
    assert await _my_role(ac, alice) == "admin"
    admin = await _admin(test_session)

    _login_cookie(ac, admin)
    resp = await ac.post(f"{API}/admin/users/{owner.id}/freeze", json={"reason": "滥用"})
    assert resp.status_code == 200, resp.text
    gs = await test_session.scalar(select(GroupServer))
    await test_session.refresh(gs)
    assert gs.status == "revoked" and gs.status_reason == REASON_BINDER_FROZEN
    assert await _my_role(ac, alice) is None

    # 复核也认冻结，不会被 EA 名单“恢复”
    await recheck_all(test_session)
    await test_session.refresh(gs)
    assert gs.status == "revoked" and gs.status_reason == REASON_BINDER_FROZEN

    # 解冻后复核按 EA 现状恢复
    _login_cookie(ac, admin)
    assert (await ac.post(f"{API}/admin/users/{owner.id}/unfreeze")).status_code == 200
    await recheck_all(test_session)
    await test_session.refresh(gs)
    assert gs.status == "active"


async def test_frozen_user_has_no_server_role_for_background_jobs(
    env,
    test_session,
    ea,  # noqa: F811
) -> None:
    ac, _, owner, alice, _, gid = await _group_with_alice(env, test_session)
    await _add_account(ac, gid)
    await _bind(ac, gid)
    admin = await _admin(test_session)
    _login_cookie(ac, admin)
    # owner 在 EA 上就是这台服的管理员，alice 靠群组拿到管理员：冻结后都没有角色
    for u in (owner, alice):
        await ac.post(f"{API}/admin/users/{u.id}/freeze", json={"reason": "x"})

    authz = ServerAuthzService(test_session)
    for uid in (owner.id, alice.id):
        user = await _load(test_session, uid)
        role, is_admin = await authz.resolve_role(user=user, game="bf1", server_id=GAME_ID)
        assert role is None and is_admin is False, uid
    user = await _load(test_session, alice.id)
    assert (
        await cp.group_server_service.executor_accounts_for(test_session, user, game_id=GAME_ID)
        == []
    )
