"""注销账号：本人申请、冷静期撤销、到期删除、平台管理员删除已冻结的账号"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models import (
    ApiKey,
    AuditLog,
    EaBinding,
    Group,
    GroupMember,
    GroupServer,
    User,
)
from app.services import account_deletion_service, api_key_service
from app.services.api_key_service import ApiKeyService
from app.services.group_server_service import REASON_BINDER_GONE
from sqlalchemy import select, update

from tests.test_accounts import _active_user, _login_cookie, _token_from
from tests.test_admin_users import _admin
from tests.test_group_servers import (  # noqa: F401  ea 是 fixture
    _add_account,
    _bind,
    _group_with_alice,
    _load,
    ea,
)

API = "/api/v1"
PW = "pw-12345678"


async def _carol(db) -> User:
    return await _active_user(db, user_id=31, email="carol@example.com", persona_id=3131)


async def _request(ac, *, password=PW, confirm="注销"):
    return await ac.post(
        f"{API}/me/delete-account", json={"password": password, "confirm": confirm}
    )


async def _expire(db, user_id: int) -> None:
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(deletion_scheduled_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await db.commit()


async def test_request_locks_account_and_cancel_restores_login(env, test_session) -> None:
    ac, outbox, _ = env
    carol = await _carol(test_session)
    _, raw = await ApiKeyService(test_session).create(carol, "bot")
    _login_cookie(ac, carol)
    old_cookie = ac.cookies.get("bfm_access_token")

    assert (await _request(ac, confirm="删除")).json()["error"]["code"] == "ACCOUNT_DELETE_CONFIRM"
    assert (await _request(ac, password="wrong")).json()["error"]["code"] == "PASSWORD_WRONG"

    resp = await _request(ac)
    assert resp.status_code == 200, resp.text
    delete_at = datetime.fromisoformat(resp.json()["delete_at"])
    assert timedelta(days=6, hours=23) < delete_at - datetime.now(UTC) <= timedelta(days=7)
    assert outbox.outbox[-1].kind == "account_deletion_scheduled"

    # 立即按冻结处理：旧会话失效、Key 吊销
    ac.cookies.set("bfm_access_token", old_cookie)
    assert (await ac.get(f"{API}/me/ea-bindings")).status_code == 401
    assert await api_key_service.resolve(test_session, raw) is None

    # 密码对了才告诉他在注销中；密码不对还是普通的 401
    ac.cookies.clear()
    login = {"email": "carol@example.com", "password": PW}
    resp = await ac.post(f"{API}/auth/email-login", json=login)
    assert resp.status_code == 403
    body = resp.json()["error"]
    assert body["code"] == "ACCOUNT_DELETION_PENDING" and body["details"]["delete_at"]
    bad = {**login, "password": "wrong-password"}
    assert (await ac.post(f"{API}/auth/email-login", json=bad)).status_code == 401
    assert (await ac.post(f"{API}/auth/cancel-deletion", json=bad)).status_code == 401

    # 撤销：解冻并登录，Key 不恢复
    resp = await ac.post(f"{API}/auth/cancel-deletion", json=login)
    assert resp.status_code == 200, resp.text
    assert (await ac.get(f"{API}/me/ea-bindings")).status_code == 200
    carol = await _load(test_session, 31)
    assert not carol.is_frozen and carol.deletion_scheduled_at is None
    assert await api_key_service.resolve(test_session, raw) is None
    actions = set(await test_session.scalars(select(AuditLog.action)))
    assert {"account_delete_request", "account_delete_cancel"} <= actions

    # 没在注销中的账号撤销会提示直接登录
    resp = await ac.post(f"{API}/auth/cancel-deletion", json=login)
    assert resp.json()["error"]["code"] == "ACCOUNT_NOT_DELETING"


async def test_platform_admin_cannot_self_delete(env, test_session) -> None:
    ac, _, _ = env
    admin = await _admin(test_session)
    _login_cookie(ac, admin)
    resp = await _request(ac)
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "ACCOUNT_DELETE_ADMIN"


async def test_sole_owner_with_members_must_hand_over_first(env, test_session, ea) -> None:  # noqa: F811
    ac, _, owner, alice, _, gid = await _group_with_alice(env, test_session)
    _login_cookie(ac, owner)
    resp = await _request(ac)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "ACCOUNT_DELETE_SOLE_OWNER"
    assert "测试 群" in resp.json()["error"]["message"]

    # 把 alice 也设成群主后就能申请
    resp = await ac.patch(f"{API}/groups/{gid}/members/{alice.id}", json={"role": "owner"})
    assert resp.status_code == 200, resp.text
    _login_cookie(ac, await _load(test_session, owner.id))
    assert (await _request(ac)).status_code == 200


async def test_due_deletion_purges_account(env, test_session) -> None:
    ac, outbox, _ = env
    carol = await _carol(test_session)
    await ApiKeyService(test_session).create(carol, "bot")
    _login_cookie(ac, carol)
    assert (await _request(ac)).status_code == 200
    # 还没到期：不删
    assert await account_deletion_service.purge_due(test_session) == 0
    assert await test_session.get(User, 31) is not None

    await _expire(test_session, 31)
    assert await account_deletion_service.purge_due(test_session) == 1
    test_session.expire_all()
    assert await test_session.get(User, 31) is None
    assert await test_session.scalar(select(EaBinding.id).where(EaBinding.user_id == 31)) is None
    assert await test_session.scalar(select(ApiKey.id).where(ApiKey.user_id == 31)) is None
    # 审计记录保留、IP 清掉；删除本身记一条
    request_log = await test_session.scalar(
        select(AuditLog).where(AuditLog.action == "account_delete_request")
    )
    assert request_log is not None and request_log.ip is None
    done = await test_session.scalar(select(AuditLog).where(AuditLog.action == "account_delete"))
    assert done.payload["target_user_id"] == 31 and done.payload["by"] == "self"
    assert outbox.outbox[-1].kind == "account_deleted"

    # 邮箱和 EA 账号都空出来了，可以重新注册
    again = await _active_user(test_session, user_id=32, email="carol@example.com", persona_id=3131)
    assert again.id == 32


async def test_cancelled_deletion_is_not_purged(env, test_session) -> None:
    ac, _, _ = env
    carol = await _carol(test_session)
    _login_cookie(ac, carol)
    assert (await _request(ac)).status_code == 200
    login = {"email": "carol@example.com", "password": PW}
    assert (await ac.post(f"{API}/auth/cancel-deletion", json=login)).status_code == 200
    # 到期查询之后才撤销的：锁住重读时发现已撤销，不删
    assert await account_deletion_service._purge_if_due(test_session, 31) is None
    assert await test_session.get(User, 31) is not None


async def test_purge_hands_over_or_dissolves_groups(env, test_session, ea) -> None:  # noqa: F811
    ac, _, owner, alice, bob, gid = await _group_with_alice(env, test_session)
    alice_id = alice.id
    await _add_account(ac, gid)
    assert (await _bind(ac, gid)).status_code == 201
    # bob 自己建一个只有他的群
    _login_cookie(ac, bob)
    solo = (await ac.post(f"{API}/groups", json={"name": "单人群"})).json()["id"]

    admin = await _admin(test_session)
    admin_id = admin.id
    _login_cookie(ac, admin)
    for u in (owner, bob):
        resp = await ac.post(f"{API}/admin/users/{u.id}/freeze", json={"reason": "x"})
        assert resp.status_code == 200
        assert (await ac.post(f"{API}/admin/users/{u.id}/delete")).status_code == 204

    test_session.expire_all()
    heir = await test_session.scalar(
        select(GroupMember).where(GroupMember.group_id == gid, GroupMember.user_id == alice_id)
    )
    assert heir.role == "owner"
    gs = await test_session.scalar(select(GroupServer).where(GroupServer.group_id == gid))
    assert gs.status == "revoked" and gs.status_reason == REASON_BINDER_GONE
    assert gs.bound_by_user_id is None
    assert await test_session.get(Group, solo) is None
    group_actions = {
        (a, g)
        for a, g in (await test_session.execute(select(AuditLog.action, AuditLog.group_id))).all()
    }
    assert ("group_owner_inherit", gid) in group_actions
    assert ("group_member_account_deleted", gid) in group_actions
    assert ("group_member_account_deleted", solo) not in group_actions
    assert ("group_delete", solo) in group_actions
    log = await test_session.scalar(
        select(AuditLog).where(AuditLog.action == "account_delete", AuditLog.user_id == admin_id)
    )
    assert log.payload["by"] == "admin"


async def test_admin_delete_rules(env, test_session) -> None:
    ac, _, _ = env
    admin = await _admin(test_session)
    carol = await _carol(test_session)
    _login_cookie(ac, admin)

    resp = await ac.post(f"{API}/admin/users/31/delete")
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "USER_DELETE_NOT_FROZEN"
    resp = await ac.post(f"{API}/admin/users/{admin.id}/delete")
    assert resp.json()["error"]["code"] == "USER_DELETE_SELF"
    assert (await ac.post(f"{API}/admin/users/404/delete")).status_code == 404

    # 注销冷静期的账号：列表能看到计划删除时间；后台不能解冻，可以直接删
    _login_cookie(ac, carol)
    assert (await _request(ac)).status_code == 200
    _login_cookie(ac, admin)
    item = (await ac.get(f"{API}/admin/users", params={"q": "carol"})).json()["items"][0]
    assert item["is_frozen"] and item["deletion_scheduled_at"]
    resp = await ac.post(f"{API}/admin/users/31/unfreeze")
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "USER_DELETION_PENDING"
    assert (await ac.post(f"{API}/admin/users/31/delete")).status_code == 204
    test_session.expire_all()
    assert await test_session.get(User, 31) is None


async def test_password_reset_allowed_during_cooldown(env, test_session) -> None:
    ac, outbox, _ = env
    carol = await _carol(test_session)
    _login_cookie(ac, carol)
    assert (await _request(ac)).status_code == 200
    ac.cookies.clear()

    resp = await ac.post(f"{API}/auth/password-reset", json={"email": "carol@example.com"})
    assert resp.status_code == 202
    token = _token_from(outbox)
    resp = await ac.post(
        f"{API}/auth/verifications/confirm", json={"token": token, "password": "new-pass-123"}
    )
    # 密码改好了，但不发会话：回登录页撤销注销
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "ACCOUNT_DELETION_PENDING"
    assert "bfm_access_token" not in resp.cookies
    assert outbox.outbox[-1].kind == "password_changed"
    login = {"email": "carol@example.com", "password": "new-pass-123"}
    assert (await ac.post(f"{API}/auth/cancel-deletion", json=login)).status_code == 200


async def test_admin_frozen_account_still_cannot_reset_password(env, test_session) -> None:
    ac, outbox, _ = env
    admin = await _admin(test_session)
    await _carol(test_session)
    _login_cookie(ac, admin)
    assert (await ac.post(f"{API}/admin/users/31/freeze", json={"reason": "x"})).status_code == 200
    ac.cookies.clear()
    sent = len(outbox.outbox)
    await ac.post(f"{API}/auth/password-reset", json={"email": "carol@example.com"})
    assert len(outbox.outbox) == sent
