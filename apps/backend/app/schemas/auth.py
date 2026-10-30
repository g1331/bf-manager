"""认证相关 schema"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class CookieBindRequest(BaseModel):
    remid: str = Field(..., min_length=10, description="EA 长效 cookie（必填）")
    # sid 可留空：EA 在 /connect/auth 响应里会 Set-Cookie 一个新 sid，
    # 只要 remid 有效就能完成登录
    sid: str = Field(default="", description="EA 短期 cookie（可选）")


class EmailLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=256)


class RegisterRequest(BaseModel):
    email: EmailStr
    # ea：填 EA 账号的邮箱，验证信同时证明邮箱和 EA 账号归你；
    # plain：用任意邮箱注册，之后再用 remid 或 EA 账号密码绑定
    mode: Literal["ea", "plain"] = "ea"
    invite_code: str | None = Field(default=None, max_length=32)
    # 群邀请链接里的 token：当注册资格用（不用邀请码），注册完成后自动进群
    group_invite_token: str | None = Field(default=None, max_length=128)


class EmailOnlyRequest(BaseModel):
    email: EmailStr


class VerificationTokenRequest(BaseModel):
    token: str = Field(..., min_length=16, max_length=128)


class VerificationConfirmRequest(VerificationTokenRequest):
    password: str = Field(..., min_length=1, max_length=256)


class VerificationInfoResponse(BaseModel):
    kind: Literal["register", "claim", "reset", "set_email"]
    email: str
    persona_name: str | None = None
    # register 时区分 EA 邮箱注册（ea）还是其他邮箱注册（plain）
    mode: Literal["ea", "plain"] | None = None


class AuthConfigResponse(BaseModel):
    """注册、登录页需要的公开配置"""

    # open 开放注册 / invite 邀请注册 / closed 暂停注册（旧账号认领照常）
    registration_mode: Literal["open", "invite", "closed"]
    invite_required: bool
    # 为空表示没启用人机验证，前端不加载 Turnstile
    turnstile_site_key: str | None = None


class AcceptedResponse(BaseModel):
    message: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=1, max_length=256)


class CookieBindResponse(BaseModel):
    # true：这个 EA 号原来挂在旧账号上，已经把邮箱和密码挪过去，需要重新登录
    claimed: bool = False
    persona_id: int
    display_name: str | None = None


class InviteCodeItem(BaseModel):
    id: int
    code: str
    status: Literal["unused", "used", "expired", "revoked"]
    expires_at: datetime
    used_at: datetime | None = None
    created_at: datetime
    # 群邀请链接注册时记下的名额占用，不是能发给别人的码
    via_group_link: bool = False


class InviteCodeListResponse(BaseModel):
    items: list[InviteCodeItem]
    # 还能生成几个；管理员不限，为 null
    quota_left: int | None = None
    invite_required: bool


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
    email: str | None = None
    # legacy：旧版 remid 登录建的号，还没设置邮箱；pending_binding：还没绑 EA
    status: Literal["legacy", "pending_binding", "active"] = "active"
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
