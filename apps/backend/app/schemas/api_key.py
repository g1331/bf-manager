"""开放 API Key 请求 / 响应 schema"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ApiKeyItem(BaseModel):
    id: int
    name: str
    prefix: str = Field(..., description="key 开头几位，用来认出是哪个 key")
    rate_multiplier: int = Field(..., description="实际生效的额度倍数")
    custom_multiplier: bool = Field(..., description="管理员是否单独调过倍数")
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None
    used_today: int
    used_7d: int


class ApiKeyQuota(BaseModel):
    """倍数为 1 时的基础额度，实际额度 = 基础额度 × key 的倍数"""

    lookup_per_minute: int
    lookup_per_day: int
    read_per_minute: int
    read_per_day: int
    avatar_per_minute: int


class ApiKeyListResponse(BaseModel):
    items: list[ApiKeyItem]
    max_keys: int
    quota: ApiKeyQuota


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=32, description="用途备注，比如机器人名字")


class ApiKeyCreated(BaseModel):
    item: ApiKeyItem
    key: str = Field(..., description="完整 key，只在创建时返回这一次")


class AdminApiKeyItem(ApiKeyItem):
    user_id: int
    user_username: str
    user_display_name: str | None


class AdminApiKeyListResponse(BaseModel):
    items: list[AdminApiKeyItem]
    default_multiplier: int


class ApiKeyUpdateRequest(BaseModel):
    rate_multiplier: int | None = Field(None, ge=1, le=50, description="额度倍数；传 null 恢复默认")
