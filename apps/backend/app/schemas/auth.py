"""认证相关 schema"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    remid: str = Field(..., min_length=10, description="EA 长效 cookie")
    sid: str = Field(..., min_length=10, description="EA 短期 cookie")


class SessionUser(BaseModel):
    """会话用户信息（绝不包含任何凭据字段）"""

    id: int
    persona_id: int
    display_name: str | None = None
    avatar_url: str | None = None
    role: Literal["user", "admin"] = "user"
    last_login_at: datetime | None = None


class LoginResponse(BaseModel):
    user: SessionUser


class SessionResponse(BaseModel):
    user: SessionUser | None = None
