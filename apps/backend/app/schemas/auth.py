"""认证相关 schema"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    remid: str = Field(..., min_length=10, description="EA 长效 cookie（必填）")
    # sid 可留空：EA 在 /connect/auth 响应里会 Set-Cookie 一个新 sid，
    # 只要 remid 有效就能完成登录
    sid: str = Field(default="", description="EA 短期 cookie（可选）")


class LocalLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1)


class SessionBinding(BaseModel):
    """会话用户的 primary binding 摘要（绝不包含任何凭据字段）"""

    id: int
    persona_id: int
    display_name: str | None = None
    avatar_url: str | None = None
    is_primary: bool
    is_frozen: bool


class SessionUser(BaseModel):
    """会话用户信息（绝不包含任何凭据字段）"""

    id: int
    username: str
    role: Literal["user", "admin"] = "user"
    is_frozen: bool = False
    last_login_at: datetime | None = None
    primary_binding: SessionBinding | None = None


class LoginResponse(BaseModel):
    user: SessionUser


class SessionResponse(BaseModel):
    user: SessionUser | None = None


class BindingListItem(BaseModel):
    id: int
    persona_id: int
    display_name: str | None = None
    avatar_url: str | None = None
    is_primary: bool
    is_frozen: bool
    last_verified_at: datetime | None = None


class BindingListResponse(BaseModel):
    items: list[BindingListItem]
