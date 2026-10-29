"""开放 API Key 路由：用户自助签发 / 吊销，平台 admin 查看全部并调整额度"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentAdmin, CurrentUser, DbDep
from app.core.config import get_settings
from app.models import ApiKey
from app.schemas.api_key import (
    AdminApiKeyItem,
    AdminApiKeyListResponse,
    ApiKeyCreated,
    ApiKeyCreateRequest,
    ApiKeyItem,
    ApiKeyListResponse,
    ApiKeyQuota,
    ApiKeyUpdateRequest,
)
from app.services.api_key_service import ApiKeyService, effective_multiplier, read_usage

me_router = APIRouter()
admin_router = APIRouter()


def _item(key: ApiKey, usage: dict[int, tuple[int, int]]) -> ApiKeyItem:
    today, week = usage.get(key.id, (0, 0))
    return ApiKeyItem(
        id=key.id,
        name=key.name,
        prefix=key.prefix,
        rate_multiplier=effective_multiplier(key),
        custom_multiplier=key.rate_multiplier is not None,
        created_at=key.created_at,
        last_used_at=key.last_used_at,
        revoked_at=key.revoked_at,
        used_today=today,
        used_7d=week,
    )


def _admin_item(key: ApiKey, usage: dict[int, tuple[int, int]]) -> AdminApiKeyItem:
    primary = next((b for b in key.user.ea_bindings if b.is_primary), None)
    return AdminApiKeyItem(
        **_item(key, usage).model_dump(),
        user_id=key.user_id,
        user_username=key.user.username,
        user_display_name=primary.display_name if primary else None,
    )


@me_router.get("", response_model=ApiKeyListResponse)
async def list_my_keys(user: CurrentUser, db: DbDep) -> ApiKeyListResponse:
    settings = get_settings()
    keys = await ApiKeyService(db).list_for_user(user.id)
    usage = await read_usage([k.id for k in keys])
    return ApiKeyListResponse(
        items=[_item(k, usage) for k in keys],
        max_keys=settings.api_key_max_per_user,
        quota=ApiKeyQuota(
            lookup_per_minute=settings.rate_limit_lookup_per_minute,
            lookup_per_day=settings.rate_limit_lookup_per_day,
            read_per_minute=settings.rate_limit_read_per_minute,
            read_per_day=settings.rate_limit_read_per_day,
            avatar_per_minute=settings.rate_limit_avatar_per_minute,
        ),
    )


@me_router.post("", response_model=ApiKeyCreated, status_code=201)
async def create_my_key(
    payload: ApiKeyCreateRequest, user: CurrentUser, db: DbDep
) -> ApiKeyCreated:
    key, raw = await ApiKeyService(db).create(user, payload.name)
    return ApiKeyCreated(item=_item(key, {}), key=raw)


@me_router.post("/{key_id}/revoke", response_model=ApiKeyItem)
async def revoke_my_key(key_id: int, user: CurrentUser, db: DbDep) -> ApiKeyItem:
    service = ApiKeyService(db)
    key = await service.revoke(await service.get(key_id, user_id=user.id))
    return _item(key, await read_usage([key.id]))


@admin_router.get("", response_model=AdminApiKeyListResponse)
async def list_all_keys(_admin: CurrentAdmin, db: DbDep) -> AdminApiKeyListResponse:
    keys = await ApiKeyService(db).list_all()
    usage = await read_usage([k.id for k in keys])
    return AdminApiKeyListResponse(
        items=[_admin_item(k, usage) for k in keys],
        default_multiplier=get_settings().rate_limit_api_key_multiplier,
    )


@admin_router.patch("/{key_id}", response_model=ApiKeyItem)
async def update_key(
    key_id: int, payload: ApiKeyUpdateRequest, _admin: CurrentAdmin, db: DbDep
) -> ApiKeyItem:
    service = ApiKeyService(db)
    key = await service.set_multiplier(await service.get(key_id), payload.rate_multiplier)
    return _item(key, await read_usage([key.id]))


@admin_router.post("/{key_id}/revoke", response_model=ApiKeyItem)
async def revoke_key(key_id: int, _admin: CurrentAdmin, db: DbDep) -> ApiKeyItem:
    service = ApiKeyService(db)
    key = await service.revoke(await service.get(key_id))
    return _item(key, await read_usage([key.id]))
