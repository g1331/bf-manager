"""群组：建群、成员角色规则、邀请链接、靠群邀请注册、群组记录"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models import GroupMember, InviteCode, User
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from tests.test_accounts import _active_user, _login_cookie, _token_from

API = "/api/v1"


async def _setup(env, db):
    ac, outbox, _directory = env
    owner = await _active_user(db, user_id=21, email="owner@example.com", persona_id=2001)
    alice = await _active_user(db, user_id=22, email="alice@example.com", persona_id=2002)
    bob = await _active_user(db, user_id=23, email="bob@example.com", persona_id=2003)
    _login_cookie(ac, owner)
    resp = await ac.post(f"{API}/groups", json={"name": "  测试   群 "})
    assert resp.status_code == 201, resp.text
    group = resp.json()
    assert group["name"] == "测试 群"
    assert group["my_role"] == "owner"
    return ac, outbox, owner, alice, bob, group["id"]


async def _invite(ac, gid, role="admin", max_uses=1) -> str:
    resp = await ac.post(
        f"{API}/groups/{gid}/invites", json={"role": role, "max_uses": max_uses, "ttl_hours": 24}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["token"]


async def _join(ac, user, token):
    _login_cookie(ac, user)
    return await ac.post(f"{API}/group-invites/accept", json={"token": token})


async def test_invite_link_lookup_accept_and_use_limit(env, test_session) -> None:
    ac, _, _owner, alice, bob, gid = await _setup(env, test_session)
    token = await _invite(ac, gid, role="admin", max_uses=1)

    # 没登录也能看是哪个群在邀请
    ac.cookies.clear()
    info = (await ac.post(f"{API}/group-invites/lookup", json={"token": token})).json()
    assert info["group_name"] == "测试 群"
    assert info["role"] == "admin"
    assert info["uses_left"] == 1
    assert info["can_register"] is True

    resp = await _join(ac, alice, token)
    assert resp.json() == {"group_id": gid, "role": "admin", "already_member": False}
    # 已经在群里：不消耗名额（这里名额已经用完，也照样返回已是成员）
    resp = await _join(ac, bob, token)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "GROUP_INVITE_INVALID"

    # 非成员看群 404
    _login_cookie(ac, bob)
    assert (await ac.get(f"{API}/groups/{gid}")).status_code == 404


async def test_already_member_does_not_consume_use(env, test_session) -> None:
    ac, _, owner, alice, _, gid = await _setup(env, test_session)
    token = await _invite(ac, gid, max_uses=2)
    assert (await _join(ac, alice, token)).json()["already_member"] is False
    assert (await _join(ac, alice, token)).json()["already_member"] is True
    _login_cookie(ac, owner)
    items = (await ac.get(f"{API}/groups/{gid}/invites")).json()["items"]
    assert items[0]["uses"] == 1


async def test_role_rules_for_admin_and_last_owner(env, test_session) -> None:
    ac, _, owner, alice, bob, gid = await _setup(env, test_session)
    await _join(ac, alice, await _invite_as(ac, owner, gid, "admin"))
    await _join(ac, bob, await _invite_as(ac, owner, gid, "admin"))

    # 群里只有群主和管理员两级，旧的协管 / 观察员不再接受
    _login_cookie(ac, owner)
    for role in ("moderator", "viewer"):
        resp = await ac.post(
            f"{API}/groups/{gid}/invites", json={"role": role, "max_uses": 1, "ttl_hours": 24}
        )
        assert resp.status_code == 422
        resp = await ac.patch(f"{API}/groups/{gid}/members/{bob.id}", json={"role": role})
        assert resp.status_code == 422
    # 链接不能直接给群主
    resp = await ac.post(
        f"{API}/groups/{gid}/invites", json={"role": "owner", "max_uses": 1, "ttl_hours": 24}
    )
    assert resp.status_code == 422

    # 管理员：看得到成员和群组记录，发不了链接、管不了任何人
    _login_cookie(ac, alice)
    assert (await ac.get(f"{API}/groups/{gid}")).json()["my_role"] == "admin"
    assert (await ac.get(f"{API}/groups/{gid}/audit")).status_code == 200
    assert (await ac.get(f"{API}/groups/{gid}/invites")).status_code == 403
    resp = await ac.post(
        f"{API}/groups/{gid}/invites", json={"role": "admin", "max_uses": 1, "ttl_hours": 24}
    )
    assert resp.status_code == 403
    assert (
        await ac.patch(f"{API}/groups/{gid}/members/{bob.id}", json={"role": "owner"})
    ).status_code == 403
    assert (await ac.delete(f"{API}/groups/{gid}/members/{bob.id}")).status_code == 403
    assert (await ac.delete(f"{API}/groups/{gid}/members/{owner.id}")).status_code == 403
    assert (await ac.patch(f"{API}/groups/{gid}", json={"name": "改名"})).status_code == 403
    assert (await ac.delete(f"{API}/groups/{gid}")).status_code == 403

    # 群主移出管理员
    _login_cookie(ac, owner)
    assert (await ac.delete(f"{API}/groups/{gid}/members/{bob.id}")).status_code == 200

    # 唯一的群主不能退群、不能把自己降级
    resp = await ac.post(f"{API}/groups/{gid}/leave")
    assert resp.json()["error"]["code"] == "GROUP_LAST_OWNER"
    resp = await ac.patch(f"{API}/groups/{gid}/members/{owner.id}", json={"role": "admin"})
    assert resp.json()["error"]["code"] == "GROUP_LAST_OWNER"
    # 先把 alice 设成群主，再退
    assert (
        await ac.patch(f"{API}/groups/{gid}/members/{alice.id}", json={"role": "owner"})
    ).status_code == 200
    assert (await ac.post(f"{API}/groups/{gid}/leave")).status_code == 204

    _login_cookie(ac, alice)
    audit = (await ac.get(f"{API}/groups/{gid}/audit")).json()
    actions = [i["action"] for i in audit["items"]]
    assert actions[0] == "group_leave"
    assert {"group_create", "group_member_join", "group_member_role", "group_member_remove"} <= set(
        actions
    )
    role_change = next(i for i in audit["items"] if i["action"] == "group_member_role")
    assert role_change["target_name"] == "P2002"
    assert "ip" not in role_change["payload"]


async def _invite_as(ac, user, gid, role):
    _login_cookie(ac, user)
    return await _invite(ac, gid, role=role)


async def test_register_through_group_invite_joins_and_uses_quota(env, test_session) -> None:
    ac, outbox, owner, _, _, gid = await _setup(env, test_session)
    token = await _invite(ac, gid)

    ac.cookies.clear()
    resp = await ac.post(
        f"{API}/auth/register",
        json={"email": "newbie@example.com", "mode": "plain", "group_invite_token": token},
    )
    assert resp.status_code == 202
    mail = outbox.outbox[-1]
    assert "测试 群" in mail.text
    resp = await ac.post(
        f"{API}/auth/verifications/confirm",
        json={"token": _token_from(outbox), "password": "newbie-pass1"},
    )
    assert resp.status_code == 200, resp.text
    new_id = resp.json()["user"]["id"]
    member = await test_session.scalar(
        select(GroupMember).where(GroupMember.group_id == gid, GroupMember.user_id == new_id)
    )
    assert member is not None and member.role == "admin"
    quota_row = await test_session.scalar(
        select(InviteCode).where(InviteCode.created_by == owner.id, InviteCode.used_by == new_id)
    )
    assert quota_row is not None
    # 邀请人的邀请码列表里，这条占用标成「群邀请链接注册」，不当成能发出去的码
    ac.cookies.clear()
    _login_cookie(ac, owner)
    items = (await ac.get(f"{API}/me/invite-codes")).json()["items"]
    assert [i["via_group_link"] for i in items if i["code"] == quota_row.code] == [True]


async def _register_mail(ac, outbox, email: str, token: str) -> str:
    resp = await ac.post(
        f"{API}/auth/register",
        json={"email": email, "mode": "plain", "group_invite_token": token},
    )
    assert resp.status_code == 202
    return _token_from(outbox)


async def test_one_use_link_cannot_register_two_accounts(env, test_session) -> None:
    """一次性链接在有人完成注册前发出了两封验证信：只有先完成的能建号，后一个整体回滚"""
    ac, outbox, owner, _, _, gid = await _setup(env, test_session)
    token = await _invite(ac, gid, max_uses=1)
    ac.cookies.clear()
    first = await _register_mail(ac, outbox, "first@example.com", token)
    second = await _register_mail(ac, outbox, "second@example.com", token)

    resp = await ac.post(
        f"{API}/auth/verifications/confirm", json={"token": first, "password": "first-pass1"}
    )
    assert resp.status_code == 200, resp.text
    ac.cookies.clear()
    resp = await ac.post(
        f"{API}/auth/verifications/confirm", json={"token": second, "password": "second-pass1"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVITE_INVALID"

    emails = {
        m.user.email
        for m in (
            await test_session.scalars(
                select(GroupMember)
                .options(selectinload(GroupMember.user))
                .where(GroupMember.group_id == gid)
            )
        ).all()
    }
    assert emails == {"owner@example.com", "first@example.com"}
    assert (
        await test_session.scalar(select(User.id).where(User.email == "second@example.com")) is None
    )
    # 只记了一次名额
    used = await test_session.scalars(select(InviteCode).where(InviteCode.created_by == owner.id))
    assert len(used.all()) == 1


async def test_revoked_link_blocks_pending_registration(env, test_session) -> None:
    """验证信发出后链接被作废：旧验证信不能再建号"""
    ac, outbox, owner, _, _, gid = await _setup(env, test_session)
    token = await _invite(ac, gid, max_uses=3)
    invite_id = (await ac.get(f"{API}/groups/{gid}/invites")).json()["items"][0]["id"]
    ac.cookies.clear()
    mail_token = await _register_mail(ac, outbox, "late@example.com", token)

    _login_cookie(ac, owner)
    assert (await ac.post(f"{API}/groups/{gid}/invites/{invite_id}/revoke")).status_code == 204
    ac.cookies.clear()
    resp = await ac.post(
        f"{API}/auth/verifications/confirm", json={"token": mail_token, "password": "late-pass12"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVITE_INVALID"
    assert (
        await test_session.scalar(select(User.id).where(User.email == "late@example.com")) is None
    )


async def test_group_invite_cannot_register_when_creator_out_of_quota(env, test_session) -> None:
    ac, _outbox, owner, _, _, gid = await _setup(env, test_session)
    token = await _invite(ac, gid)
    now = datetime.now(UTC)
    for i in range(5):
        test_session.add(
            InviteCode(
                code=f"FULL-{i:04d}", created_by=owner.id, expires_at=now + timedelta(days=1)
            )
        )
    await test_session.commit()

    ac.cookies.clear()
    info = (await ac.post(f"{API}/group-invites/lookup", json={"token": token})).json()
    assert info["can_register"] is False
    resp = await ac.post(
        f"{API}/auth/register",
        json={"email": "x@example.com", "mode": "plain", "group_invite_token": token},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "GROUP_INVITE_NO_QUOTA"


async def test_delete_group_and_creation_limit(env, test_session, monkeypatch) -> None:
    from app.core.config import get_settings

    ac, _, _owner, _, _, gid = await _setup(env, test_session)
    monkeypatch.setattr(get_settings(), "group_owned_limit_per_user", 1)
    assert (await ac.get(f"{API}/groups")).json()["create_left"] == 0
    resp = await ac.post(f"{API}/groups", json={"name": "第二个"})
    assert resp.json()["error"]["code"] == "GROUP_LIMIT"
    assert (await ac.delete(f"{API}/groups/{gid}")).status_code == 204
    assert (await ac.get(f"{API}/groups")).json()["items"] == []
