"""认证路由：邮箱密码登录 / 注册 / 验证链接 / 找回密码 / 本地管理员登录 / 会话 / 登出

旧版的 remid 登录（POST /auth/login）已经下线：remid / sid 只用来绑定 EA（/me/ea-bindings/cookie）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Cookie, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.client_ip import client_ip
from app.api.deps import (
    CurrentUserAnyStatus,
    CurrentUserOptional,
    DbDep,
    SessionFactoryDep,
)
from app.api.errors import UnauthorizedError
from app.api.rate_limit import rate_limit
from app.api.turnstile import require_turnstile, turnstile_enabled
from app.core.config import get_settings
from app.core.security import JWTError, create_access_token, decode_access_token
from app.models import User
from app.schemas.auth import (
    AcceptedResponse,
    AuthConfigResponse,
    EmailLoginRequest,
    EmailOnlyRequest,
    LocalLoginRequest,
    LoginResponse,
    RegisterRequest,
    SessionBinding,
    SessionResponse,
    SessionUser,
    VerificationConfirmRequest,
    VerificationInfoResponse,
    VerificationTokenRequest,
)
from app.services import (
    account_deletion_service,
    account_service,
    login_throttle,
    site_settings_service,
)
from app.services.account_service import AccountError, normalize_email, primary_binding
from app.services.auth_service import AuthService

router = APIRouter()


COOKIE_NAME = "bfm_access_token"

# 滑动续期：会话 token 签发超过这么久，/session 就换发一张新的。
# 前端每次打开都会查 /session，所以常用的人不会掉线，长期不用才需要重新登录。
SESSION_RENEW_AFTER = timedelta(hours=24)

# 注册、找回密码一律返回这句话，不透露邮箱有没有 EA 号、有没有注册过
MAIL_ACCEPTED = "如果信息无误，邮件几分钟内就会送到，请查收（也看看垃圾箱）。"


def build_session_user(user: User) -> SessionUser:
    primary = primary_binding(user)
    return SessionUser(
        id=user.id,
        username=user.username,
        role=user.role,  # type: ignore[arg-type]
        email=user.email,
        status=user.status,  # type: ignore[arg-type]
        is_frozen=user.is_frozen,
        last_login_at=user.last_login_at,
        primary_binding=(
            SessionBinding(
                id=primary.id,
                persona_id=primary.persona_id,
                display_name=primary.display_name,
                avatar_url=primary.avatar_url,
                is_primary=primary.is_primary,
                is_frozen=primary.is_frozen,
            )
            if primary is not None
            else None
        ),
    )


def issue_session(response: Response, user: User) -> None:
    """签发会话 JWT 并写入 httpOnly cookie。sv 和 users.token_version 对不上的会话会被拒。"""
    settings = get_settings()
    token = create_access_token(
        subject=user.id, extra_claims={"role": user.role, "sv": user.token_version}
    )
    expires_in_minutes = settings.jwt_access_token_expire_minutes
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=expires_in_minutes * 60,
        expires=datetime.now(UTC) + timedelta(minutes=expires_in_minutes),
        path="/",
        secure=settings.is_production,
        httponly=True,
        samesite="lax",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def _token_needs_renewal(token: str) -> bool:
    try:
        issued_at = decode_access_token(token).get("iat")
    except JWTError:
        return False
    if not isinstance(issued_at, int):
        return True
    return datetime.now(UTC) - datetime.fromtimestamp(issued_at, UTC) >= SESSION_RENEW_AFTER


async def _load_user_with_bindings(db: DbDep, user_id: int) -> User | None:
    result: User | None = await db.scalar(
        select(User).options(selectinload(User.ea_bindings)).where(User.id == user_id)
    )
    return result


@router.get("/config", response_model=AuthConfigResponse, dependencies=[rate_limit("read")])
async def auth_config(db: DbDep) -> AuthConfigResponse:
    settings = get_settings()
    mode = await site_settings_service.get_registration_mode(db)
    return AuthConfigResponse(
        registration_mode=mode,
        invite_required=mode == "invite",
        turnstile_site_key=settings.turnstile_site_key if turnstile_enabled() else None,
    )


@router.post("/email-login", response_model=LoginResponse)
async def email_login(
    payload: EmailLoginRequest,
    db: DbDep,
    request: Request,
    response: Response,
) -> LoginResponse:
    """邮箱 + 密码登录。失败统一 401，同一邮箱或 IP 失败过多先返回 429。"""
    email = normalize_email(payload.email)
    ip = client_ip(request)
    await login_throttle.ensure_not_locked(email, ip)
    try:
        user = await account_service.login_with_email(db, email, payload.password)
    except UnauthorizedError:
        await login_throttle.record_failure(email, ip)
        raise
    await login_throttle.clear(email)
    issue_session(response, user)
    return LoginResponse(user=build_session_user(user))


@router.post("/cancel-deletion", response_model=LoginResponse)
async def cancel_deletion(
    payload: EmailLoginRequest,
    db: DbDep,
    request: Request,
    response: Response,
) -> LoginResponse:
    """注销冷静期内撤销注销并登录。和邮箱登录共用失败计数"""
    email = normalize_email(payload.email)
    ip = client_ip(request)
    await login_throttle.ensure_not_locked(email, ip)
    try:
        user = await account_deletion_service.cancel_deletion(db, email, payload.password, ip)
    except UnauthorizedError:
        await login_throttle.record_failure(email, ip)
        raise
    await login_throttle.clear(email)
    issue_session(response, user)
    full_user = await _load_user_with_bindings(db, user.id)
    if full_user is None:
        raise UnauthorizedError("会话建立失败")
    return LoginResponse(user=build_session_user(full_user))


@router.post("/local-login", response_model=LoginResponse)
async def local_login(
    payload: LocalLoginRequest,
    db: DbDep,
    request: Request,
    response: Response,
) -> LoginResponse:
    """本地账号 username + password 登录（CLI 创建的本地 admin 专用）。

    与邮箱登录颁发同名 `bfm_access_token` cookie，下游鉴权中间件不区分入口来源。
    校验失败统一返回 401，不区分「用户不存在」与「密码错误」。
    同一用户名或 IP 失败过多时先返回 429，见 login_throttle。
    """
    service = AuthService(db)
    ip = client_ip(request)
    await login_throttle.ensure_not_locked(payload.username, ip)
    try:
        user = await service.login_with_local_password(payload.username, payload.password)
    except UnauthorizedError:
        await login_throttle.record_failure(payload.username, ip)
        raise
    await login_throttle.clear(payload.username)

    issue_session(response, user)

    full_user = await _load_user_with_bindings(db, user.id)
    if full_user is None:
        raise UnauthorizedError("会话建立失败")
    return LoginResponse(user=build_session_user(full_user))


@router.post(
    "/register",
    status_code=202,
    dependencies=[rate_limit("account_mail"), require_turnstile()],
    response_model=AcceptedResponse,
)
async def register(
    payload: RegisterRequest,
    db: DbDep,
    request: Request,
    background: BackgroundTasks,
    session_factory: SessionFactoryDep,
) -> AcceptedResponse:
    """申请注册。查 EA、查重、发信都在后台做，这里只校验邀请码（邀请码本身不涉及邮箱信息）。

    没填邀请码时照样受理：EA 号挂在旧账号上的认领、“账号已存在”的提醒都不需要邀请码；
    真要新建账号又没有邀请码时，后台不发信。
    """
    invite_id: int | None = None
    group_invite_id: int | None = None
    registration = await site_settings_service.get_registration_mode(db)
    if registration == "closed":
        # 暂停注册：其他邮箱注册一定是新建账号，直接拒；EA 邮箱照常受理，旧账号还能认领，
        # 后台判断出要新建账号时不发信。邀请码、群链接这时都用不上，不校验
        if payload.mode == "plain":
            raise AccountError("REGISTRATION_CLOSED", "现在暂停注册，暂时不能新建账号", 403)
    elif payload.group_invite_token and payload.group_invite_token.strip():
        group_invite_id = (
            await account_service.check_group_invite_for_register(
                db, payload.group_invite_token.strip()
            )
        ).id
    elif registration == "invite" and payload.invite_code and payload.invite_code.strip():
        # 开放注册时带了邀请码（比如点的是旧的邀请链接）也不看，免得过期的码挡住注册
        invite_id = (await account_service.check_invite_code(db, payload.invite_code)).id
    background.add_task(
        account_service.process_register_request,
        session_factory,
        email=normalize_email(payload.email),
        mode=payload.mode,
        invite_id=invite_id,
        group_invite_id=group_invite_id,
        ip=client_ip(request),
    )
    return AcceptedResponse(message=MAIL_ACCEPTED)


@router.post(
    "/password-reset",
    status_code=202,
    dependencies=[rate_limit("account_mail"), require_turnstile()],
    response_model=AcceptedResponse,
)
async def request_password_reset(
    payload: EmailOnlyRequest,
    request: Request,
    background: BackgroundTasks,
    session_factory: SessionFactoryDep,
) -> AcceptedResponse:
    background.add_task(
        account_service.process_reset_request,
        session_factory,
        email=normalize_email(payload.email),
        ip=client_ip(request),
    )
    return AcceptedResponse(message=MAIL_ACCEPTED)


# 验证链接是 /verify#token=…：token 放在 # 后面，不会出现在任何访问日志里；
# 页面用 POST 把 token 交给下面两个接口。查看不消耗 token，提交密码才消耗。


@router.post(
    "/verifications/lookup",
    response_model=VerificationInfoResponse,
    dependencies=[rate_limit("account_link")],
)
async def lookup_verification(
    payload: VerificationTokenRequest, db: DbDep
) -> VerificationInfoResponse:
    info = await account_service.get_verification_info(db, payload.token)
    return VerificationInfoResponse(
        kind=info.kind,  # type: ignore[arg-type]
        email=info.email,
        persona_name=info.persona_name,
        mode=info.mode,  # type: ignore[arg-type]
    )


@router.post(
    "/verifications/confirm",
    response_model=LoginResponse,
    dependencies=[rate_limit("account_link")],
)
async def confirm_verification(
    payload: VerificationConfirmRequest,
    db: DbDep,
    request: Request,
    response: Response,
    background: BackgroundTasks,
) -> LoginResponse:
    """设置密码并完成注册 / 认领 / 重置 / 补邮箱，完成后直接登录。"""
    info = await account_service.get_verification_info(db, payload.token)
    user = await account_service.confirm_verification(db, payload.token, payload.password)
    if user.deletion_scheduled_at is not None:
        # 注销冷静期内找回了密码：密码已改好，不发会话，回登录页撤销注销后再进来。
        # 接口以错误返回时后台任务不会跑，通知信直接发
        if user.email:
            await account_service.send_password_changed(user.email, client_ip(request))
        raise account_service.pending_deletion_error(user)
    if info.kind == "reset" and user.email:
        background.add_task(account_service.send_password_changed, user.email, client_ip(request))
    issue_session(response, user)
    return LoginResponse(user=build_session_user(user))


@router.get("/session", response_model=SessionResponse)
async def session(
    user: CurrentUserOptional,
    response: Response,
    access_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> SessionResponse:
    # get_current_user 已经 eager-load 了 ea_bindings，无需再查
    if user is None:
        return SessionResponse(user=None)
    if access_token and _token_needs_renewal(access_token):
        issue_session(response, user)
    return SessionResponse(user=build_session_user(user))


@router.post("/logout", status_code=204)
async def logout(_user: CurrentUserAnyStatus, response: Response) -> None:
    clear_session(response)


@router.post("/logout-all", status_code=204)
async def logout_all(user: CurrentUserAnyStatus, db: DbDep, response: Response) -> None:
    """登出所有设备：会话版本加一，之前签发的所有会话（包括这一个）都失效。"""
    await account_service.revoke_sessions(db, user)
    clear_session(response)
