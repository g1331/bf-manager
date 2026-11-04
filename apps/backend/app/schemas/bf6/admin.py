"""BF6 凭据的后台接口 schema。只回状态，不回任何凭据原值。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Bf6CredentialStatusResponse(BaseModel):
    configured: bool
    refresh_expires_at: datetime | None = None
    access_expires_at: datetime | None = None
    last_refreshed_at: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None
    updated_at: datetime | None = None


class Bf6CredentialUpdate(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=16384)
    # 留空沿用已保存的值；首次保存必填
    client_secret: str | None = Field(default=None, max_length=512)
