"""FastAPI 依赖：DB 会话、当前用户、游戏 profile"""

from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, Path
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.errors import AppError, ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import decode_access_token
from app.db.session import get_db, get_sessionmaker
from app.domain.games.base import GameProfile
from app.domain.games.registry import GameRegistry
from app.models import User
from app.services.account_service import SessionFactory

DbDep = Annotated[AsyncSession, Depends(get_db)]


def get_session_factory() -> SessionFactory:
    """后台任务自己开 session 用（请求的 session 在响应后就关了）。测试里换成测试库。"""
    return get_sessionmaker()


SessionFactoryDep = Annotated[SessionFactory, Depends(get_session_factory)]


async def get_current_user_any_status(
    db: DbDep,
    access_token: Annotated[str | None, Cookie(alias="bfm_access_token")] = None,
) -> User:
    """解析会话，不看账号状态。只给“还没绑 EA 也要能用”的接口：会话、登出、绑定 EA。"""
    if not access_token:
        raise UnauthorizedError()
    try:
        payload = decode_access_token(access_token)
    except JWTError as e:
        raise UnauthorizedError("会话无效，请重新登录") from e

    sub = payload.get("sub")
    if not sub:
        raise UnauthorizedError()
    try:
        user_id = int(sub)
    except ValueError as e:
        raise UnauthorizedError() from e

    user = await db.scalar(
        select(User).options(selectinload(User.ea_bindings)).where(User.id == user_id)
    )
    if user is None or not user.is_active or user.is_frozen:
        raise UnauthorizedError()
    # 改密码、登出所有设备会把 token_version 加一，之前签发的会话全部失效。
    # 这个字段上线前签发的 token 没有 sv，按 0 处理
    if payload.get("sv", 0) != user.token_version:
        raise UnauthorizedError("会话已失效，请重新登录")
    return user


async def get_current_user(
    user: Annotated[User, Depends(get_current_user_any_status)],
) -> User:
    """当前登录用户。还没绑 EA 的账号（pending_binding）只能先去绑定。"""
    if user.status == "pending_binding":
        raise AppError(403, "ACCOUNT_PENDING_BINDING", "请先绑定 EA 账号")
    return user


async def get_current_user_optional(
    db: DbDep,
    access_token: Annotated[str | None, Cookie(alias="bfm_access_token")] = None,
) -> User | None:
    if not access_token:
        return None
    try:
        return await get_current_user_any_status(db=db, access_token=access_token)
    except UnauthorizedError:
        return None


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentUserAnyStatus = Annotated[User, Depends(get_current_user_any_status)]
CurrentUserOptional = Annotated[User | None, Depends(get_current_user_optional)]


async def get_current_admin(user: CurrentUser) -> User:
    """与 ``get_current_user`` 链路一致，再额外要求 ``role == 'admin'``。

    保持与 ``ea_accounts.py::_require_admin`` 相同的 403 文案，方便前端按错误码与
    文案统一处理。
    """
    if user.role != "admin":
        raise ForbiddenError(message="仅平台管理员可执行此操作")
    return user


CurrentAdmin = Annotated[User, Depends(get_current_admin)]


def get_game_profile(game: Annotated[str, Path()]) -> GameProfile:
    if not GameRegistry.has(game):
        raise NotFoundError(resource=f"游戏 {game}")
    return GameRegistry.get(game)


GameProfileDep = Annotated[GameProfile, Depends(get_game_profile)]
