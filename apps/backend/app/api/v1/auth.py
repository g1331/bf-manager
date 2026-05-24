"""认证路由：EA Cookie 登录 / 会话 / 登出"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request, Response

from app.api.deps import CurrentUser, CurrentUserOptional, DbDep
from app.core.config import get_settings
from app.core.security import create_access_token
from app.schemas.auth import LoginRequest, LoginResponse, SessionResponse, SessionUser
from app.services.auth_service import AuthService

router = APIRouter()


COOKIE_NAME = "bfm_access_token"


def _build_session_user(user) -> SessionUser:
    return SessionUser(
        id=user.id,
        persona_id=user.persona_id,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        role=user.role,
        last_login_at=user.last_login_at,
    )


def _set_session_cookie(response: Response, token: str, *, expires_in_minutes: int) -> None:
    settings = get_settings()
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


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    db: DbDep,
    response: Response,
) -> LoginResponse:
    """使用 EA Cookie (remid + sid) 登录"""
    settings = get_settings()
    service = AuthService(db)
    user = await service.login_with_cookie(payload.remid, payload.sid)

    token = create_access_token(
        subject=user.id,
        extra_claims={"persona_id": user.persona_id, "role": user.role},
    )
    _set_session_cookie(
        response, token, expires_in_minutes=settings.jwt_access_token_expire_minutes
    )
    return LoginResponse(user=_build_session_user(user))


@router.get("/session", response_model=SessionResponse)
async def session(user: CurrentUserOptional) -> SessionResponse:
    if user is None:
        return SessionResponse(user=None)
    return SessionResponse(user=_build_session_user(user))


@router.post("/logout", status_code=204)
async def logout(_user: CurrentUser, _request: Request, response: Response) -> Response:
    response.delete_cookie(COOKIE_NAME, path="/")
    return Response(status_code=204)
