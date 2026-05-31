"""EA 服管账号管理路由（仅平台 admin 可访问）。

写入接收明文凭据并即时加密存储，读取只暴露健康状态，绝不回显任何明文凭据。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbDep
from app.api.errors import ForbiddenError
from app.models import User
from app.schemas.ea_account import (
    EAAccountCreate,
    EAAccountCredentialsUpdate,
    EAAccountDisplayNameUpdate,
    EAAccountEnabledUpdate,
    EAAccountItem,
    EAAccountVerifyResult,
)
from app.services.ea_account_service import EAAccountService

router = APIRouter()


def _require_admin(user: User) -> None:
    if user.role != "admin":
        raise ForbiddenError(message="仅平台管理员可管理 EA 账号")


@router.get("", response_model=list[EAAccountItem])
async def list_ea_accounts(db: DbDep, user: CurrentUser) -> list[EAAccountItem]:
    _require_admin(user)
    return await EAAccountService(db).list_all()


@router.post("", response_model=EAAccountItem, status_code=201)
async def create_ea_account(
    payload: EAAccountCreate,
    db: DbDep,
    user: CurrentUser,
) -> EAAccountItem:
    _require_admin(user)
    return await EAAccountService(db).create(payload)


@router.patch("/{account_id}/credentials", response_model=EAAccountItem)
async def update_ea_account_credentials(
    account_id: int,
    payload: EAAccountCredentialsUpdate,
    db: DbDep,
    user: CurrentUser,
) -> EAAccountItem:
    _require_admin(user)
    return await EAAccountService(db).update_credentials(account_id, payload)


@router.patch("/{account_id}/enabled", response_model=EAAccountItem)
async def set_ea_account_enabled(
    account_id: int,
    payload: EAAccountEnabledUpdate,
    db: DbDep,
    user: CurrentUser,
) -> EAAccountItem:
    _require_admin(user)
    return await EAAccountService(db).set_enabled(account_id, payload.enabled)


@router.patch("/{account_id}/display-name", response_model=EAAccountItem)
async def update_ea_account_display_name(
    account_id: int,
    payload: EAAccountDisplayNameUpdate,
    db: DbDep,
    user: CurrentUser,
) -> EAAccountItem:
    _require_admin(user)
    return await EAAccountService(db).update_display_name(account_id, payload)


@router.delete("/{account_id}", status_code=204)
async def delete_ea_account(account_id: int, db: DbDep, user: CurrentUser) -> None:
    _require_admin(user)
    await EAAccountService(db).delete(account_id)


@router.post("/{account_id}/verify", response_model=EAAccountVerifyResult)
async def verify_ea_account(
    account_id: int,
    db: DbDep,
    user: CurrentUser,
) -> EAAccountVerifyResult:
    _require_admin(user)
    return await EAAccountService(db).verify(account_id)
