"""平台运维统计、站点设置路由（仅平台 admin 可访问）。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.client_ip import client_ip
from app.api.deps import CurrentAdmin, DbDep
from app.models import User
from app.schemas.admin import (
    AdminMetrics,
    RegistrationSettingRequest,
    RegistrationSettingResponse,
)
from app.services import site_settings_service
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
