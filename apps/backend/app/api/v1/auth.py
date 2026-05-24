"""认证路由（最小骨架，M1 阶段会填充完整登录链路）"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.deps import CurrentUser, CurrentUserOptional, DbDep
from app.schemas.auth import LoginRequest, LoginResponse, SessionResponse, SessionUser

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login(
    _payload: LoginRequest,
    _db: DbDep,
    _response: Response,
) -> LoginResponse:
    """EA Cookie 登录。M1 阶段实现完整登录链路，此处暂为占位。"""
    raise NotImplementedError("Login flow is implemented in M1")


@router.get("/session", response_model=SessionResponse)
async def session(user: CurrentUserOptional) -> SessionResponse:
    if user is None:
        return SessionResponse(user=None)
    return SessionResponse(
        user=SessionUser(
            id=user.id,
            persona_id=user.persona_id,
            display_name=user.display_name,
            avatar_url=user.avatar_url,
            role=user.role,  # type: ignore[arg-type]
            last_login_at=user.last_login_at,
        )
    )


@router.post("/logout", status_code=204)
async def logout(_user: Annotated[CurrentUser, Depends()], response: Response) -> Response:
    response.delete_cookie("bfm_access_token", path="/")
    return Response(status_code=204)
