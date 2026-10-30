"""注册方式开关：开放 / 邀请 / 暂停，后台切换后下一个请求生效"""

from __future__ import annotations

from app.core.config import get_settings
from app.models import AuditLog, GroupMember, InviteCode, User
from app.services import site_settings_service
from app.services.account_service import EaEmailMatch
from sqlalchemy import func, select

from tests.test_accounts import (
    EA_EMAIL,
    PERSONA,
    _active_user,
    _legacy_user,
    _login_cookie,
    _token_from,
)

API = "/api/v1"


async def _admin(db) -> User:
    admin = await _active_user(db, user_id=90, email="root@example.com", persona_id=9090)
    admin.role = "admin"
    await db.commit()
    return admin


async def _set_mode(ac, db, mode: str) -> None:
    _login_cookie(ac, await db.get(User, 90) or await _admin(db))
    resp = await ac.put(f"{API}/admin/settings/registration", json={"mode": mode})
    assert resp.status_code == 200, resp.text
    assert resp.json()["mode"] == mode
    ac.cookies.clear()


async def _confirm(ac, token: str, password: str = "pass-word-123"):
    return await ac.post(
        f"{API}/auth/verifications/confirm", json={"token": token, "password": password}
    )


async def test_default_follows_env_until_admin_sets_it(env, test_session, monkeypatch) -> None:
    ac, _, _ = env
    cfg = (await ac.get(f"{API}/auth/config")).json()
    assert cfg["registration_mode"] == "invite"
    assert cfg["invite_required"] is True

    monkeypatch.setattr(get_settings(), "registration_invite_required", False)
    assert (await ac.get(f"{API}/auth/config")).json()["registration_mode"] == "open"

    admin = await _admin(test_session)
    _login_cookie(ac, admin)
    body = (await ac.get(f"{API}/admin/settings/registration")).json()
    assert body["mode"] == "open" and body["is_default"] is True

    # 后台设过以后不再跟环境变量走
    resp = await ac.put(f"{API}/admin/settings/registration", json={"mode": "closed"})
    body = resp.json()
    assert body["mode"] == "closed" and body["is_default"] is False
    assert body["updated_by_name"] == "P9090"
    monkeypatch.setattr(get_settings(), "registration_invite_required", True)
    cfg = (await ac.get(f"{API}/auth/config")).json()
    assert cfg["registration_mode"] == "closed"
    assert cfg["invite_required"] is False

    log = await test_session.scalar(
        select(AuditLog).where(AuditLog.action == "site_registration_mode")
    )
    assert log is not None and log.game == "site" and log.user_id == admin.id
    assert log.payload == {"from": "open", "to": "closed"}


async def test_only_platform_admin_can_change(env, test_session) -> None:
    ac, _, _ = env
    user = await _active_user(test_session, user_id=31, email="u@example.com", persona_id=3131)
    _login_cookie(ac, user)
    assert (await ac.get(f"{API}/admin/settings/registration")).status_code == 403
    resp = await ac.put(f"{API}/admin/settings/registration", json={"mode": "open"})
    assert resp.status_code == 403
    ac.cookies.clear()
    resp = await ac.put(f"{API}/admin/settings/registration", json={"mode": "open"})
    assert resp.status_code == 401
    admin = await _admin(test_session)
    _login_cookie(ac, admin)
    resp = await ac.put(f"{API}/admin/settings/registration", json={"mode": "everyone"})
    assert resp.status_code == 422
    assert await site_settings_service.get_registration_mode(test_session) == "invite"


async def test_open_mode_registers_without_invite(env, test_session) -> None:
    ac, outbox, _ = env
    await _set_mode(ac, test_session, "open")
    resp = await ac.post(
        f"{API}/auth/register", json={"email": "free@example.com", "mode": "plain"}
    )
    assert resp.status_code == 202
    resp = await _confirm(ac, _token_from(outbox))
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["status"] == "pending_binding"


async def test_closed_mode_blocks_new_accounts_but_keeps_claims(env, test_session) -> None:
    ac, outbox, directory = env
    # 暂停前发出的验证信
    await _set_mode(ac, test_session, "open")
    await ac.post(f"{API}/auth/register", json={"email": "early@example.com", "mode": "plain"})
    early_token = _token_from(outbox)
    sent = len(outbox.outbox)

    await _set_mode(ac, test_session, "closed")
    # 其他邮箱注册一定是新账号：直接拒
    resp = await ac.post(f"{API}/auth/register", json={"email": "new@example.com", "mode": "plain"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "REGISTRATION_CLOSED"
    # EA 邮箱但不是旧账号：照常 202，不发信（和其他情形同一个响应，不泄露邮箱是否存在）
    directory["fresh@example.com"] = EaEmailMatch(1000000000777, 1000000000778, "Fresh")
    resp = await ac.post(f"{API}/auth/register", json={"email": "fresh@example.com", "mode": "ea"})
    assert resp.status_code == 202
    assert len(outbox.outbox) == sent

    # 旧账号认领照常
    legacy = await _legacy_user(test_session)
    directory["player@example.com"] = EaEmailMatch(PERSONA, 1000331701469, "OldTimer")
    resp = await ac.post(f"{API}/auth/register", json={"email": EA_EMAIL, "mode": "ea"})
    assert resp.status_code == 202
    assert outbox.outbox[-1].kind == "claim"
    resp = await _confirm(ac, _token_from(outbox))
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["id"] == legacy.id

    # 暂停前发出的注册信，暂停后不能再建号
    ac.cookies.clear()
    resp = await _confirm(ac, early_token)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "REGISTRATION_CLOSED"
    assert (
        await test_session.scalar(select(User.id).where(User.email == "early@example.com")) is None
    )


async def _group_with_link(ac, db, *, owner_id: int = 41) -> tuple[User, int, str]:
    owner = await _active_user(db, user_id=owner_id, email="gowner@example.com", persona_id=4141)
    _login_cookie(ac, owner)
    gid = (await ac.post(f"{API}/groups", json={"name": "开关测试"})).json()["id"]
    resp = await ac.post(
        f"{API}/groups/{gid}/invites", json={"role": "admin", "max_uses": 3, "ttl_hours": 24}
    )
    ac.cookies.clear()
    return owner, gid, resp.json()["token"]


async def test_group_link_follows_registration_mode(env, test_session, monkeypatch) -> None:
    ac, outbox, _ = env
    owner, gid, token = await _group_with_link(ac, test_session)
    # 发链接人的邀请名额用完
    monkeypatch.setattr(get_settings(), "invite_quota_per_user", 0)

    lookup = lambda: ac.post(f"{API}/group-invites/lookup", json={"token": token})  # noqa: E731
    assert (await lookup()).json()["can_register"] is False

    await _set_mode(ac, test_session, "closed")
    assert (await lookup()).json()["can_register"] is False

    # 开放注册：不看名额，注册也不占名额，照样进群
    await _set_mode(ac, test_session, "open")
    assert (await lookup()).json()["can_register"] is True
    resp = await ac.post(
        f"{API}/auth/register",
        json={"email": "joiner@example.com", "mode": "plain", "group_invite_token": token},
    )
    assert resp.status_code == 202
    resp = await _confirm(ac, _token_from(outbox))
    assert resp.status_code == 200, resp.text
    new_id = resp.json()["user"]["id"]
    member = await test_session.scalar(
        select(GroupMember).where(GroupMember.group_id == gid, GroupMember.user_id == new_id)
    )
    assert member is not None
    used = await test_session.scalar(
        select(func.count()).select_from(InviteCode).where(InviteCode.created_by == owner.id)
    )
    assert used == 0


async def test_confirm_follows_mode_at_confirm_time(env, test_session) -> None:
    ac, outbox, _ = env
    # 开放注册时发的信没带邀请码，确认前改成邀请注册：不能建号
    await _set_mode(ac, test_session, "open")
    await ac.post(f"{API}/auth/register", json={"email": "slow@example.com", "mode": "plain"})
    open_token = _token_from(outbox)
    await _set_mode(ac, test_session, "invite")
    resp = await _confirm(ac, open_token)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "INVITE_REQUIRED"
    assert (
        await test_session.scalar(select(User.id).where(User.email == "slow@example.com")) is None
    )

    # 邀请注册时带码发的信，确认前改成开放注册：照常建号，码不占用
    inviter = await _active_user(test_session, user_id=51, email="inv@example.com", persona_id=5151)
    _login_cookie(ac, inviter)
    code = (await ac.post(f"{API}/me/invite-codes")).json()["items"][0]["code"]
    ac.cookies.clear()
    await ac.post(
        f"{API}/auth/register",
        json={"email": "coded@example.com", "mode": "plain", "invite_code": code},
    )
    coded_token = _token_from(outbox)
    await _set_mode(ac, test_session, "open")
    resp = await _confirm(ac, coded_token)
    assert resp.status_code == 200, resp.text
    invite = await test_session.scalar(select(InviteCode).where(InviteCode.code == code))
    await test_session.refresh(invite)
    assert invite.used_at is None


async def test_open_mode_ignores_stale_invite_code(env, test_session) -> None:
    ac, outbox, _ = env
    await _set_mode(ac, test_session, "open")
    resp = await ac.post(
        f"{API}/auth/register",
        json={"email": "stale@example.com", "mode": "plain", "invite_code": "DEAD-BEEF"},
    )
    assert resp.status_code == 202
    resp = await _confirm(ac, _token_from(outbox))
    assert resp.status_code == 200, resp.text


async def test_audit_chain_records_actual_previous_mode(env, test_session) -> None:
    ac, _, _ = env
    for mode in ("open", "closed", "invite", "open"):
        await _set_mode(ac, test_session, mode)
    logs = (
        await test_session.scalars(
            select(AuditLog)
            .where(AuditLog.action == "site_registration_mode")
            .order_by(AuditLog.id)
        )
    ).all()
    assert [(log.payload["from"], log.payload["to"]) for log in logs] == [
        ("invite", "open"),
        ("open", "closed"),
        ("closed", "invite"),
        ("invite", "open"),
    ]
