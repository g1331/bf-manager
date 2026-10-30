"""群组接口的请求与响应"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

GroupRole = Literal["owner", "admin"]
# 链接上的角色要低于发链接的群主，所以只能是 admin；保留字段，以后加角色时接口不用改
InviteRole = Literal["admin"]


class GroupCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)


class GroupRenameRequest(GroupCreateRequest):
    pass


class GroupSummaryItem(BaseModel):
    id: int
    name: str
    my_role: GroupRole
    member_count: int
    created_at: datetime


class GroupListResponse(BaseModel):
    items: list[GroupSummaryItem]
    # 还能再建几个；平台管理员不限，为 null
    create_left: int | None


class GroupMemberItem(BaseModel):
    user_id: int
    username: str
    display_name: str | None
    avatar_url: str | None
    persona_id: int | None
    role: GroupRole
    # 还没绑 EA 的成员在群里没有权限，前端标出来
    pending_binding: bool
    joined_at: datetime
    is_me: bool


class GroupDetailResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    my_role: GroupRole
    members: list[GroupMemberItem]


class MemberRoleRequest(BaseModel):
    role: GroupRole


class InviteCreateRequest(BaseModel):
    role: InviteRole = "admin"
    max_uses: int = Field(1, ge=1, le=100)
    ttl_hours: int = 168


class GroupInviteItem(BaseModel):
    id: int
    role: InviteRole
    max_uses: int
    uses: int
    expires_at: datetime
    created_at: datetime
    created_by_name: str | None


class InviteCreateResponse(BaseModel):
    invite: GroupInviteItem
    # 明文 token，只在创建时返回一次；前端拼成 /invite#token=…
    token: str


class InviteListResponse(BaseModel):
    items: list[GroupInviteItem]


class InviteTokenRequest(BaseModel):
    token: str = Field(..., min_length=16, max_length=128)


class InviteLookupResponse(BaseModel):
    group_name: str
    role: InviteRole
    member_count: int
    inviter_name: str | None
    expires_at: datetime
    uses_left: int
    # 能不能拿这个链接注册新账号（发链接人还有邀请名额）
    can_register: bool


class InviteAcceptResponse(BaseModel):
    group_id: int
    role: GroupRole
    already_member: bool


class GroupAuditItem(BaseModel):
    id: int
    action: str
    actor_name: str | None
    target_name: str | None
    payload: dict[str, Any]
    created_at: datetime


class GroupAuditPage(BaseModel):
    items: list[GroupAuditItem]
    total: int
    page: int
    page_size: int
