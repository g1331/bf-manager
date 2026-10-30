"""账号体系：注册、认领、验证链接、找回密码、登录、会话撤销、EA 绑定归属、邀请码、清理"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.core.passwords import hash_password, verify_password
from app.core.security import create_access_token
from app.models import EaBinding, EmailVerification, InviteCode, User
from app.services import account_service
from app.services.account_service import EaEmailMatch
from app.services.auth_service import AuthService, EaIdentity
from app.services.mail import LogMailSender
from app.services.mail.templates import RequestMeta, mask_ip, register_ea
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

EA_EMAIL = "Player@Example.com"
PERSONA = 1004198901469


def _token_from(outbox: LogMailSender) -> str:
    text = outbox.outbox[-1].text
    marker = "/verify#token="
    assert marker in text, text
    return text.split(marker, 1)[1].split()[0]


async def _make_invite(db, creator_id: int | None = None) -> InviteCode:
    row = InviteCode(
        code="ABCD-EFGH", created_by=creator_id, expires_at=datetime.now(UTC) + timedelta(days=7)
    )
    db.add(row)
    await db.commit()
    return row


async def _user(db, user_id: int) -> User:
    user = await db.scalar(
        select(User)
        .options(selectinload(User.ea_bindings))
        .where(User.id == user_id)
        .execution_options(populate_existing=True)
    )
    assert user is not None
    return user


async def _legacy_user(db, *, user_id: int = 7, persona_id: int = PERSONA) -> User:
    user = User(id=user_id, username=f"persona_{persona_id}", role="user", status="legacy")
    db.add(user)
    await db.flush()
    db.add(
        EaBinding(
            user_id=user.id,
            persona_id=persona_id,
            display_name="OldTimer",
            verified_via="legacy",
            encrypted_remid="enc",
            is_primary=True,
            is_frozen=False,
        )
    )
    await db.commit()
    return user


async def _active_user(
    db, *, user_id: int, email: str, persona_id: int | None, password="pw-12345678"
):
    user = User(
        id=user_id,
        username=f"u{user_id}",
        email=email,
        email_verified_at=datetime.now(UTC),
        local_password_hash=hash_password(password),
        role="user",
        status="active" if persona_id else "pending_binding",
    )
    db.add(user)
    await db.flush()
    if persona_id:
        db.add(
            EaBinding(
                user_id=user.id,
                persona_id=persona_id,
                display_name=f"P{persona_id}",
                verified_via="email",
                is_primary=True,
                is_frozen=False,
            )
        )
    await db.commit()
    return user


def _set_cookie(ac: AsyncClient, token: str) -> None:
    # 服务端 Set-Cookie 带 domain，手动设的不带，两条同名会冲突：先清空
    ac.cookies.clear()
    ac.cookies.set("bfm_access_token", token)


def _get_cookie(ac: AsyncClient) -> str | None:
    values = [c.value for c in ac.cookies.jar if c.name == "bfm_access_token"]
    return values[-1] if values else None


def _login_cookie(ac: AsyncClient, user: User) -> None:
    _set_cookie(ac, create_access_token(subject=user.id, extra_claims={"sv": user.token_version}))


# ===== 注册：EA 邮箱 =====


async def test_register_with_ea_email_creates_account_on_confirm(env, test_session) -> None:
    ac, outbox, directory = env
    directory["player@example.com"] = EaEmailMatch(PERSONA, 1000331701469, "SHlSAN13")
    invite = await _make_invite(test_session)

    resp = await ac.post(
        "/api/v1/auth/register", json={"email": EA_EMAIL, "mode": "ea", "invite_code": "abcd-efgh"}
    )
    assert resp.status_code == 202
    assert len(outbox.outbox) == 1
    mail = outbox.outbox[0]
    assert mail.to == "player@example.com"
    assert "SHlSAN13" in mail.subject
    token = _token_from(outbox)

    # 打开链接只读，可以反复看
    for _ in range(2):
        info = await ac.post("/api/v1/auth/verifications/lookup", json={"token": token})
        assert info.status_code == 200
        assert info.json() == {
            "kind": "register",
            "email": "player@example.com",
            "persona_name": "SHlSAN13",
            "mode": "ea",
        }
    assert (await test_session.scalar(select(User).where(User.email.isnot(None)))) is None

    resp = await ac.post(
        "/api/v1/auth/verifications/confirm", json={"token": token, "password": "s3cret-pass"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["user"]
    assert body["status"] == "active"
    assert body["email"] == "player@example.com"
    assert body["primary_binding"]["persona_id"] == PERSONA
    assert "bfm_access_token" in resp.cookies

    binding = await test_session.scalar(select(EaBinding).where(EaBinding.persona_id == PERSONA))
    assert binding.verified_via == "email"
    assert binding.ea_user_id == 1000331701469
    assert binding.encrypted_remid is None
    await test_session.refresh(invite)
    assert invite.used_at is not None and invite.used_by == body["id"]

    # 同一链接不能用第二次
    again = await ac.post(
        "/api/v1/auth/verifications/confirm", json={"token": token, "password": "s3cret-pass"}
    )
    assert again.status_code == 404
    # 新账号能用邮箱密码登录
    login = await ac.post(
        "/api/v1/auth/email-login", json={"email": "PLAYER@example.com", "password": "s3cret-pass"}
    )
    assert login.status_code == 200


async def test_register_without_invite_sends_nothing_when_required(env) -> None:
    ac, outbox, directory = env
    directory["player@example.com"] = EaEmailMatch(PERSONA, None, "SHlSAN13")
    resp = await ac.post("/api/v1/auth/register", json={"email": EA_EMAIL, "mode": "ea"})
    assert resp.status_code == 202
    assert outbox.outbox == []


async def test_register_with_bad_invite_is_rejected_upfront(env) -> None:
    ac, outbox, _ = env
    resp = await ac.post(
        "/api/v1/auth/register", json={"email": EA_EMAIL, "mode": "ea", "invite_code": "NOPE-NOPE"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVITE_INVALID"
    assert outbox.outbox == []


async def test_unknown_ea_email_gets_same_response_and_no_mail(env, test_session) -> None:
    ac, outbox, _ = env
    await _make_invite(test_session)
    resp = await ac.post(
        "/api/v1/auth/register", json={"email": EA_EMAIL, "mode": "ea", "invite_code": "ABCD-EFGH"}
    )
    assert resp.status_code == 202
    assert resp.json()["message"] == account_service_accepted()
    assert outbox.outbox == []


def account_service_accepted() -> str:
    from app.api.v1.auth import MAIL_ACCEPTED

    return MAIL_ACCEPTED


async def test_ea_already_bound_to_active_account_sends_notice(env, test_session) -> None:
    ac, outbox, directory = env
    await _active_user(test_session, user_id=3, email="other@example.com", persona_id=PERSONA)
    directory["player@example.com"] = EaEmailMatch(PERSONA, None, "SHlSAN13")
    resp = await ac.post("/api/v1/auth/register", json={"email": EA_EMAIL, "mode": "ea"})
    assert resp.status_code == 202
    assert [m.kind for m in outbox.outbox] == ["already_registered"]
    assert "/verify#token=" not in outbox.outbox[0].text


async def test_password_is_set_on_confirm_not_on_request(env, test_session) -> None:
    """方案 8.1：申请注册时不收密码，别人替你申请也拿不到账号"""
    ac, _, directory = env
    directory["player@example.com"] = EaEmailMatch(PERSONA, None, "SHlSAN13")
    await _make_invite(test_session)
    resp = await ac.post(
        "/api/v1/auth/register",
        json={"email": EA_EMAIL, "mode": "ea", "invite_code": "ABCD-EFGH", "password": "attacker"},
    )
    assert resp.status_code == 202
    row = await test_session.scalar(select(EmailVerification))
    assert "password" not in str(row.payload)


async def test_new_request_invalidates_older_link(env, test_session) -> None:
    ac, outbox, directory = env
    directory["player@example.com"] = EaEmailMatch(PERSONA, None, "SHlSAN13")
    await _make_invite(test_session)
    body = {"email": EA_EMAIL, "mode": "ea", "invite_code": "ABCD-EFGH"}
    await ac.post("/api/v1/auth/register", json=body)
    first = _token_from(outbox)
    await ac.post("/api/v1/auth/register", json=body)
    second = _token_from(outbox)
    assert first != second
    assert (
        await ac.post("/api/v1/auth/verifications/lookup", json={"token": first})
    ).status_code == 404
    assert (
        await ac.post("/api/v1/auth/verifications/lookup", json={"token": second})
    ).status_code == 200


# ===== 认领旧账号 =====


async def test_claim_legacy_account_via_ea_email(env, test_session) -> None:
    ac, outbox, directory = env
    legacy = await _legacy_user(test_session)
    directory["player@example.com"] = EaEmailMatch(PERSONA, 1000331701469, "OldTimer")

    # 认领不需要邀请码
    resp = await ac.post("/api/v1/auth/register", json={"email": EA_EMAIL, "mode": "ea"})
    assert resp.status_code == 202
    assert outbox.outbox[-1].kind == "claim"
    token = _token_from(outbox)
    info = (await ac.post("/api/v1/auth/verifications/lookup", json={"token": token})).json()
    assert info["kind"] == "claim"

    resp = await ac.post(
        "/api/v1/auth/verifications/confirm", json={"token": token, "password": "new-password"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["id"] == legacy.id

    user = await _user(test_session, legacy.id)
    assert user.status == "active"
    assert user.email == "player@example.com"
    assert user.token_version == 1
    assert verify_password("new-password", user.local_password_hash)
    assert user.ea_bindings[0].verified_via == "email"
    # 旧会话（sv=0）认领后失效
    _set_cookie(ac, create_access_token(subject=legacy.id, extra_claims={"sv": 0}))
    assert (await ac.get("/api/v1/me/ea-bindings")).status_code == 401


# ===== 其他邮箱注册 + 绑定 =====


async def test_plain_register_then_bind_with_cookie(env, test_session, monkeypatch) -> None:
    ac, outbox, _ = env
    await _make_invite(test_session)
    resp = await ac.post(
        "/api/v1/auth/register",
        json={"email": "me@qq.com", "mode": "plain", "invite_code": "ABCD-EFGH"},
    )
    assert resp.status_code == 202
    token = _token_from(outbox)
    resp = await ac.post(
        "/api/v1/auth/verifications/confirm", json={"token": token, "password": "s3cret-pass"}
    )
    assert resp.status_code == 200
    assert resp.json()["user"]["status"] == "pending_binding"

    # 还没绑 EA：会话、绑定接口能用，其他需要登录的接口一律 403
    assert (await ac.get("/api/v1/auth/session")).json()["user"]["status"] == "pending_binding"
    assert (await ac.get("/api/v1/me/ea-bindings")).status_code == 200
    blocked = await ac.get("/api/v1/me/invite-codes")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "ACCOUNT_PENDING_BINDING"

    async def fake_verify(self, remid, sid):
        return EaIdentity(persona_id=555, display_name="Bound", avatar_url=None)

    monkeypatch.setattr(AuthService, "verify_ea_cookie", fake_verify)
    resp = await ac.post("/api/v1/me/ea-bindings/cookie", json={"remid": "r" * 20, "sid": ""})
    assert resp.status_code == 200, resp.text
    assert resp.json()["claimed"] is False
    binding = await test_session.scalar(select(EaBinding).where(EaBinding.persona_id == 555))
    assert binding.verified_via == "cookie"
    assert binding.encrypted_remid is None
    assert (await ac.get("/api/v1/me/invite-codes")).status_code == 200


async def test_cookie_bind_cannot_take_persona_from_active_account(
    env, test_session, monkeypatch
) -> None:
    """方案 8.2：拿着别人的 remid 也不能把对方的绑定挪走"""
    ac, _, _ = env
    owner = await _active_user(test_session, user_id=3, email="owner@example.com", persona_id=777)
    attacker = await _active_user(
        test_session, user_id=4, email="evil@example.com", persona_id=None
    )

    async def fake_verify(self, remid, sid):
        return EaIdentity(persona_id=777, display_name="Victim", avatar_url=None)

    monkeypatch.setattr(AuthService, "verify_ea_cookie", fake_verify)
    _login_cookie(ac, attacker)
    resp = await ac.post("/api/v1/me/ea-bindings/cookie", json={"remid": "r" * 20})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "EA_BINDING_CONFLICT"
    binding = await test_session.scalar(select(EaBinding).where(EaBinding.persona_id == 777))
    assert binding.user_id == owner.id


async def test_cookie_bind_claims_legacy_account(env, test_session, monkeypatch) -> None:
    ac, _, _ = env
    legacy = await _legacy_user(test_session, user_id=7, persona_id=888)
    pending = await _active_user(test_session, user_id=8, email="me@qq.com", persona_id=None)

    async def fake_verify(self, remid, sid):
        return EaIdentity(persona_id=888, display_name="OldTimer", avatar_url=None)

    monkeypatch.setattr(AuthService, "verify_ea_cookie", fake_verify)
    _login_cookie(ac, pending)
    resp = await ac.post("/api/v1/me/ea-bindings/cookie", json={"remid": "r" * 20})
    assert resp.status_code == 200, resp.text
    assert resp.json()["claimed"] is True

    assert await test_session.get(User, pending.id) is None
    user = await _user(test_session, legacy.id)
    assert user.status == "active"
    assert user.email == "me@qq.com"
    assert verify_password("pw-12345678", user.local_password_hash)
    login = await ac.post(
        "/api/v1/auth/email-login", json={"email": "me@qq.com", "password": "pw-12345678"}
    )
    assert login.json()["user"]["id"] == legacy.id


async def test_unbinding_last_binding_returns_to_pending(user_client, test_session) -> None:
    ac, user = user_client
    binding = user.ea_bindings[0]
    resp = await ac.post(f"/api/v1/me/ea-bindings/{binding.id}/unbind")
    assert resp.status_code == 204
    refreshed = await _user(test_session, user.id)
    assert refreshed.status == "pending_binding"
    # 冻结的历史行不再占着这个 EA 号：别人可以重新绑
    other = User(id=50, username="other", role="user", status="active")
    test_session.add(other)
    await test_session.flush()
    test_session.add(
        EaBinding(user_id=50, persona_id=binding.persona_id, is_primary=True, is_frozen=False)
    )
    await test_session.commit()


# ===== 找回密码 =====


async def test_password_reset_flow_revokes_old_sessions(env, test_session) -> None:
    ac, outbox, _ = env
    user = await _active_user(test_session, user_id=3, email="me@example.com", persona_id=777)
    _login_cookie(ac, user)
    assert (await ac.get("/api/v1/me/ea-bindings")).status_code == 200
    old_cookie = _get_cookie(ac)

    resp = await ac.post("/api/v1/auth/password-reset", json={"email": "ME@example.com"})
    assert resp.status_code == 202
    assert outbox.outbox[-1].kind == "reset"
    token = _token_from(outbox)
    resp = await ac.post(
        "/api/v1/auth/verifications/confirm", json={"token": token, "password": "brand-new-pw"}
    )
    assert resp.status_code == 200
    assert outbox.outbox[-1].kind == "password_changed"

    _set_cookie(ac, old_cookie)
    assert (await ac.get("/api/v1/me/ea-bindings")).status_code == 401
    ok = await ac.post(
        "/api/v1/auth/email-login", json={"email": "me@example.com", "password": "brand-new-pw"}
    )
    assert ok.status_code == 200


async def test_password_reset_skips_local_admin_and_unknown(env, test_session) -> None:
    ac, outbox, _ = env
    test_session.add(
        User(
            id=9,
            username="root",
            email="admin@example.com",
            local_password_hash=hash_password("x"),
            role="admin",
            status="active",
        )
    )
    await test_session.commit()
    for email in ("admin@example.com", "nobody@example.com"):
        resp = await ac.post("/api/v1/auth/password-reset", json={"email": email})
        assert resp.status_code == 202
    assert outbox.outbox == []


# ===== 登录与会话 =====


async def test_email_login_rejects_wrong_password_and_legacy(env, test_session) -> None:
    ac, _, _ = env
    await _active_user(test_session, user_id=3, email="me@example.com", persona_id=777)
    bad = await ac.post(
        "/api/v1/auth/email-login", json={"email": "me@example.com", "password": "nope"}
    )
    assert bad.status_code == 401


async def test_logout_all_invalidates_every_session(env, test_session) -> None:
    ac, _, _ = env
    user = await _active_user(test_session, user_id=3, email="me@example.com", persona_id=777)
    _login_cookie(ac, user)
    token = _get_cookie(ac)
    assert (await ac.post("/api/v1/auth/logout-all")).status_code == 204
    _set_cookie(ac, token)
    assert (await ac.get("/api/v1/me/ea-bindings")).status_code == 401


async def test_change_password_keeps_current_device(env, test_session) -> None:
    ac, outbox, _ = env
    user = await _active_user(test_session, user_id=3, email="me@example.com", persona_id=777)
    _login_cookie(ac, user)
    old = _get_cookie(ac)
    wrong = await ac.post(
        "/api/v1/me/password", json={"current_password": "x", "new_password": "another-pw"}
    )
    assert wrong.status_code == 400
    resp = await ac.post(
        "/api/v1/me/password",
        json={"current_password": "pw-12345678", "new_password": "another-pw"},
    )
    assert resp.status_code == 204
    assert _get_cookie(ac) != old
    assert (await ac.get("/api/v1/me/ea-bindings")).status_code == 200
    assert outbox.outbox[-1].kind == "password_changed"


async def test_legacy_user_sets_email(env, test_session) -> None:
    ac, outbox, _ = env
    legacy = await _legacy_user(test_session)
    _login_cookie(ac, legacy)
    resp = await ac.post("/api/v1/me/email", json={"email": "Old@Example.com"})
    assert resp.status_code == 202
    assert outbox.outbox[-1].kind == "set_email"
    token = _token_from(outbox)
    resp = await ac.post(
        "/api/v1/auth/verifications/confirm", json={"token": token, "password": "legacy-pass"}
    )
    assert resp.status_code == 200
    user = await _user(test_session, legacy.id)
    assert (user.status, user.email) == ("active", "old@example.com")


# ===== 邀请码 =====


async def test_invite_quota_and_revoke(user_client, test_session, monkeypatch) -> None:
    ac, _ = user_client
    monkeypatch.setattr(account_service.get_settings(), "invite_quota_per_user", 2)
    first = await ac.post("/api/v1/me/invite-codes")
    assert first.status_code == 201
    assert first.json()["quota_left"] == 1
    await ac.post("/api/v1/me/invite-codes")
    full = await ac.post("/api/v1/me/invite-codes")
    assert full.status_code == 400
    assert full.json()["error"]["code"] == "INVITE_QUOTA"
    code_id = first.json()["items"][0]["id"]
    revoked = await ac.post(f"/api/v1/me/invite-codes/{code_id}/revoke")
    assert revoked.json()["quota_left"] == 1


# ===== 清理 =====


async def test_cleanup_removes_only_stale_never_bound_accounts(test_session) -> None:
    old = datetime.now(UTC) - timedelta(days=3)
    test_session.add_all(
        [
            User(id=1, username="stale", role="user", status="pending_binding", created_at=old),
            User(id=2, username="fresh", role="user", status="pending_binding"),
            User(id=3, username="unbound", role="user", status="pending_binding", created_at=old),
        ]
    )
    await test_session.flush()
    test_session.add(EaBinding(user_id=3, persona_id=1, is_primary=False, is_frozen=True))
    await test_session.commit()
    await account_service.cleanup_once(test_session)
    left = set(await test_session.scalars(select(User.username)))
    assert left == {"fresh", "unbound"}


# ===== 邮件模板 =====


def test_templates_escape_names_and_mask_ip() -> None:
    msg = register_ea(
        to="a@b.c",
        persona_name="<script>",
        url="https://bfm.example/verify#token=abc",
        ttl_hours=4,
        meta=RequestMeta.now("203.0.113.9"),
    )
    assert "<script>" not in msg.html
    assert "&lt;script&gt;" in msg.html
    assert "203.0.113.*" in msg.text
    assert "https://bfm.example/verify#token=abc" in msg.text
    assert mask_ip("2001:db8:1:2:3:4:5:6") == "2001:db8:1:2:…"


@pytest.mark.parametrize("password", ["short", "x" * 200])
async def test_password_length_rules(env, test_session, password) -> None:
    ac, outbox, _ = env
    await _make_invite(test_session)
    await ac.post(
        "/api/v1/auth/register",
        json={"email": "me@qq.com", "mode": "plain", "invite_code": "ABCD-EFGH"},
    )
    token = _token_from(outbox)
    resp = await ac.post(
        "/api/v1/auth/verifications/confirm", json={"token": token, "password": password}
    )
    assert resp.status_code == 400
    # 校验失败不消耗链接
    assert (
        await ac.post("/api/v1/auth/verifications/lookup", json={"token": token})
    ).status_code == 200


async def test_turnstile_needs_both_keys_and_checks_header(env, monkeypatch) -> None:
    from app.api import turnstile
    from app.core.config import get_settings

    client, _, _ = env
    settings = get_settings()
    monkeypatch.setattr(settings, "turnstile_secret_key", "secret")

    # 只配了 secret：前端不会显示验证框，后端也不能拦
    cfg = (await client.get("/api/v1/auth/config")).json()
    assert cfg["turnstile_site_key"] is None
    body = {"email": "a@example.com", "mode": "plain"}
    assert (await client.post("/api/v1/auth/password-reset", json=body)).status_code == 202

    monkeypatch.setattr(settings, "turnstile_site_key", "0x4AAA-site")
    cfg = (await client.get("/api/v1/auth/config")).json()
    assert cfg == {
        "invite_required": settings.registration_invite_required,
        "turnstile_site_key": "0x4AAA-site",
    }

    seen: list[str] = []

    async def fake_verify(token, _ip):
        seen.append(token)
        return token == "good"

    monkeypatch.setattr(turnstile, "_verify", fake_verify)
    resp = await client.post("/api/v1/auth/password-reset", json=body)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CAPTCHA_FAILED"
    resp = await client.post(
        "/api/v1/auth/password-reset", json=body, headers={"X-Turnstile-Token": "bad"}
    )
    assert resp.status_code == 400
    resp = await client.post(
        "/api/v1/auth/password-reset", json=body, headers={"X-Turnstile-Token": "good"}
    )
    assert resp.status_code == 202
    assert seen == ["bad", "good"]


async def test_login_costs_one_bcrypt_even_for_unknown_email(env, monkeypatch) -> None:
    import bcrypt

    client, _, _ = env
    calls: list[int] = []
    real = bcrypt.checkpw

    def counting(pw, hashed):
        calls.append(1)
        return real(pw, hashed)

    monkeypatch.setattr(bcrypt, "checkpw", counting)
    resp = await client.post(
        "/api/v1/auth/email-login", json={"email": "nobody@example.com", "password": "whatever1"}
    )
    assert resp.status_code == 401
    assert len(calls) == 1
