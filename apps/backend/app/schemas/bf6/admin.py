"""BF6 凭据的后台接口 schema。只回状态，不回任何凭据原值。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Bf6CredentialStatusResponse(BaseModel):
    configured: bool
    refresh_expires_at: datetime | None = None
    access_expires_at: datetime | None = None
    last_refreshed_at: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None
    updated_at: datetime | None = None


class Bf6CredentialUpdate(BaseModel):
    # 不在这里加长度约束：FastAPI 的 422 会把原值放进 input 回给客户端。长度在服务层校验，报错不带原值
    refresh_token: str
    # 留空沿用已保存的值；首次保存必填
    client_secret: str | None = None
