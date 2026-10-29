"""认证路由：EA Cookie 登录 / 本地账号登录 / 会话 / 登出"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Cookie, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, CurrentUserOptional, DbDep
from app.api.errors import UnauthorizedError
from app.core.config import get_settings
from app.core.security import JWTError, create_access_token, decode_access_token
from app.models import EaBinding, User
from app.schemas.auth import (
    LocalLoginRequest,
    LoginRequest,
    LoginResponse,
    SessionBinding,
    SessionResponse,
    SessionUser,
)
from app.services.auth_service import AuthService

router = APIRouter()


COOKIE_NAME = "bfm_access_token"

# 滑动续期：会话 token 签发超过这么久，/session 就换发一张新的。
# 前端每次打开都会查 /session，所以常用的人不会掉线，长期不用才需要重新登录。
SESSION_RENEW_AFTER = timedelta(hours=24)


def _primary_binding(user: User) -> EaBinding | None:
    for b in user.ea_bindings:
        if b.is_primary and not b.is_frozen:
            return b
    return None


def _build_session_user(user: User) -> SessionUser:
    primary = _primary_binding(user)
    return SessionUser(
        id=user.id,
        username=user.username,
        role=user.role,  # type: ignore[arg-type]
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


def _issue_session(response: Response, user: User) -> None:
    """签发会话 JWT 并写入 httpOnly cookie。"""
    settings = get_settings()
    token = create_access_token(subject=user.id, extra_claims={"role": user.role})
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


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    db: DbDep,
    response: Response,
) -> LoginResponse:
    """使用 EA Cookie (remid + sid) 登录。

    路径：EA cookie → 校验 → 拿到 persona_id → 找/创建 user → 更新 binding → 颁发 JWT。
    """
    service = AuthService(db)
    user, _binding = await service.login_with_cookie(payload.remid, payload.sid)

    _issue_session(response, user)

    full_user = await _load_user_with_bindings(db, user.id)
    if full_user is None:
        # 仅在 user 刚刚 commit 后被另一个事务删除时可达；此时整次登录视为失效
        raise UnauthorizedError("会话建立失败")
    return LoginResponse(user=_build_session_user(full_user))


@router.post("/local-login", response_model=LoginResponse)
async def local_login(
    payload: LocalLoginRequest,
    db: DbDep,
    response: Response,
) -> LoginResponse:
    """本地账号 username + password 登录（CLI 创建的本地 admin 专用）。

    与 EA cookie 登录颁发同名 `bfm_access_token` cookie，下游鉴权中间件不区分入口来源。
    校验失败统一返回 401，不区分「用户不存在」与「密码错误」。
    """
    service = AuthService(db)
    user = await service.login_with_local_password(payload.username, payload.password)

    _issue_session(response, user)

    full_user = await _load_user_with_bindings(db, user.id)
    if full_user is None:
        raise UnauthorizedError("会话建立失败")
    return LoginResponse(user=_build_session_user(full_user))


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
        _issue_session(response, user)
    return SessionResponse(user=_build_session_user(user))


@router.post("/logout", status_code=204)
async def logout(_user: CurrentUser, _request: Request, response: Response) -> Response:
    response.delete_cookie(COOKIE_NAME, path="/")
    return Response(status_code=204)
