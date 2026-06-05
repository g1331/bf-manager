"""FastAPI 依赖：DB 会话、当前用户、游戏 profile"""

from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, Path
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.errors import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.domain.games.base import GameProfile
from app.domain.games.registry import GameRegistry
from app.models import User

DbDep = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    db: DbDep,
    access_token: Annotated[str | None, Cookie(alias="bfm_access_token")] = None,
) -> User:
    if not access_token:
        raise UnauthorizedError()
    try:
        payload = decode_access_token(access_token)
    except JWTError as e:
        raise UnauthorizedError(f"无效的会话: {e}") from e

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
    return user


async def get_current_user_optional(
    db: DbDep,
    access_token: Annotated[str | None, Cookie(alias="bfm_access_token")] = None,
) -> User | None:
    if not access_token:
        return None
    try:
        return await get_current_user(db=db, access_token=access_token)
    except UnauthorizedError:
        return None


CurrentUser = Annotated[User, Depends(get_current_user)]
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
