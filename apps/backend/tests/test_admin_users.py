"""后台用户管理：列表、冻结、解冻，冻结后会话、API Key、群组挂服、服务器权限一并失效"""

from __future__ import annotations

import pytest
from app.api.errors import AppError
from app.domain.games.bf1 import client_provider as cp
from app.models import ApiKey, AuditLog, GroupServer, User
from app.services import api_key_service
from app.services import group_server_service as gss
from app.services.api_key_service import ApiKeyService
from app.services.authz_service import ServerAuthzService
from app.services.group_server_service import REASON_BINDER_FROZEN, recheck_all
from app.services.group_service import GroupError
from sqlalchemy import select
from sqlalchemy.orm.attributes import set_committed_value

from tests.test_accounts import _active_user, _login_cookie
from tests.test_api_keys import fake_redis  # noqa: F401  fixture
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
    # 超出整数列范围的数字照样能搜（只按文本匹配），不报错
    resp = await ac.get(f"{API}/admin/users", params={"q": "9" * 20})
    assert resp.status_code == 200 and resp.json()["total"] == 0

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


async def test_stale_cache_refill_cannot_revive_revoked_key(
    env,
    test_session,
    fake_redis,  # noqa: F811
) -> None:
    """吊销前就查过库的校验请求晚一步回填缓存，也盖不掉吊销写下的“无效”"""
    carol = await _active_user(test_session, user_id=31, email="carol@example.com", persona_id=3131)
    key, raw = await ApiKeyService(test_session).create(carol, "bot")
    real_set = fake_redis.set
    fired = False

    async def set_after_revoke(name, value, ex=None, nx=False):
        nonlocal fired
        if not fired:
            fired = True
            # 校验请求已经查完库（有效），还没写缓存时 Key 被吊销
            await ApiKeyService(test_session).revoke(key)
        return await real_set(name, value, ex=ex, nx=nx)

    fake_redis.set = set_after_revoke
    assert await api_key_service.resolve(test_session, raw) is not None
    assert await api_key_service.resolve(test_session, raw) is None


async def test_inflight_key_create_after_freeze_is_rejected(env, test_session) -> None:
    """冻结前进来的新建 Key 请求，冻结提交后才走到写库：锁住用户重读，拒绝"""
    ac, _, _ = env
    admin = await _admin(test_session)
    carol = await _active_user(test_session, user_id=31, email="carol@example.com", persona_id=3131)
    _login_cookie(ac, admin)
    assert (await ac.post(f"{API}/admin/users/31/freeze", json={"reason": "x"})).status_code == 200

    stale = await _load(test_session, carol.id)
    set_committed_value(stale, "is_frozen", False)  # 请求入口读到的还是冻结前
    with pytest.raises(AppError) as exc:
        await ApiKeyService(test_session).create(stale, "bot")
    assert exc.value.code == "ACCOUNT_FROZEN"
    await test_session.rollback()
    assert await test_session.scalar(select(ApiKey.id).where(ApiKey.user_id == 31)) is None


async def test_inflight_bind_after_freeze_is_rejected(env, test_session, ea) -> None:  # noqa: F811
    """挂服请求查完 EA 后等群锁，期间挂服人被冻结：拿到锁后重读挂服人，拒绝，挂服保持失效"""
    ac, _, owner, _, _, gid = await _group_with_alice(env, test_session)
    await _add_account(ac, gid)
    await _bind(ac, gid)
    admin = await _admin(test_session)
    _login_cookie(ac, admin)
    resp = await ac.post(f"{API}/admin/users/{owner.id}/freeze", json={"reason": "x"})
    assert resp.status_code == 200

    stale = await _load(test_session, owner.id)
    set_committed_value(stale, "is_frozen", False)
    with pytest.raises(GroupError) as exc:
        await gss.bind_server(test_session, gid, stale, game_id=GAME_ID)
    assert exc.value.code == "ACCOUNT_FROZEN"
    await test_session.rollback()
    gs = await test_session.scalar(select(GroupServer))
    await test_session.refresh(gs)
    assert gs.status == "revoked"
