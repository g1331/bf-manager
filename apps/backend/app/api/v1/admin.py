"""平台运维统计、站点设置、用户管理路由（仅平台 admin 可访问）。"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.client_ip import client_ip
from app.api.deps import CurrentAdmin, DbDep
from app.models import User
from app.schemas.admin import (
    AdminMetrics,
    AdminUserItem,
    AdminUserPage,
    RegistrationSettingRequest,
    RegistrationSettingResponse,
    UserFreezeRequest,
)
from app.services import account_deletion_service, site_settings_service, user_admin_service
from app.services.account_service import primary_binding
from app.services.metrics_service import read_metrics

router = APIRouter()


@router.get("/metrics", response_model=AdminMetrics)
async def get_admin_metrics(_user: CurrentAdmin) -> AdminMetrics:
    return await read_metrics()


async def _registration_response(
    db: DbDep, setting: site_settings_service.RegistrationSetting
) -> RegistrationSettingResponse:
    name: str | None = None
    if setting.updated_by is not None:
        user = await db.scalar(
            select(User)
            .options(selectinload(User.ea_bindings))
            .where(User.id == setting.updated_by)
        )
        if user is not None:
            binding = primary_binding(user)
            name = (binding.display_name if binding else None) or user.username
    return RegistrationSettingResponse(
        mode=setting.mode,
        is_default=setting.is_default,
        updated_at=setting.updated_at,
        updated_by_name=name,
    )


@router.get("/settings/registration", response_model=RegistrationSettingResponse)
async def get_registration_setting(_user: CurrentAdmin, db: DbDep) -> RegistrationSettingResponse:
    return await _registration_response(db, await site_settings_service.get_registration(db))


@router.put("/settings/registration", response_model=RegistrationSettingResponse)
async def set_registration_setting(
    payload: RegistrationSettingRequest, user: CurrentAdmin, db: DbDep, request: Request
) -> RegistrationSettingResponse:
    setting = await site_settings_service.set_registration_mode(
        db, payload.mode, user, ip=client_ip(request)
    )
    return await _registration_response(db, setting)


# ===== 用户 =====


def _user_item(row: user_admin_service.UserRow) -> AdminUserItem:
    user = row.user
    binding = primary_binding(user)
    return AdminUserItem(
        id=user.id,
        username=user.username,
        email=user.email,
        role="admin" if user.role == "admin" else "user",
        status=user.status,
        persona_id=binding.persona_id if binding else None,
        display_name=binding.display_name if binding else None,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        active_api_keys=row.active_keys,
        is_frozen=user.is_frozen,
        frozen_at=user.frozen_at,
        frozen_reason=user.frozen_reason,
        frozen_by_name=row.frozen_by_name,
        deletion_scheduled_at=user.deletion_scheduled_at,
    )


@router.get("/users", response_model=AdminUserPage)
async def list_users(
    _user: CurrentAdmin,
    db: DbDep,
    q: Annotated[str | None, Query(max_length=64)] = None,
    only: Annotated[Literal["frozen", "admin"] | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminUserPage:
    rows, total = await user_admin_service.list_users(
        db, q=q, only=only, page=page, page_size=page_size
    )
    return AdminUserPage(
        items=[_user_item(r) for r in rows], total=total, page=page, page_size=page_size
    )


@router.post("/users/{user_id}/freeze", response_model=AdminUserItem)
async def freeze_user(
    user_id: int, payload: UserFreezeRequest, user: CurrentAdmin, db: DbDep, request: Request
) -> AdminUserItem:
    row = await user_admin_service.freeze(db, user, user_id, payload.reason, ip=client_ip(request))
    return _user_item(row)


@router.post("/users/{user_id}/unfreeze", response_model=AdminUserItem)
async def unfreeze_user(
    user_id: int, user: CurrentAdmin, db: DbDep, request: Request
) -> AdminUserItem:
    row = await user_admin_service.unfreeze(db, user, user_id, ip=client_ip(request))
    return _user_item(row)


@router.post("/users/{user_id}/delete", status_code=204)
async def delete_user(user_id: int, user: CurrentAdmin, db: DbDep, request: Request) -> None:
    """删除已冻结的账号，立即生效、不可恢复"""
    await account_deletion_service.admin_delete(db, user, user_id, ip=client_ip(request))
