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


# ===== 服务账号与绑服 =====

AccountStatus = Literal["ok", "invalid"]


class GroupAccountItem(BaseModel):
    id: int
    persona_id: int
    display_name: str | None
    is_default: bool
    status: AccountStatus
    last_error: str | None
    last_verified_at: datetime | None
    created_at: datetime


class GroupAccountListResponse(BaseModel):
    items: list[GroupAccountItem]


class GroupAccountCookieRequest(BaseModel):
    remid: str = Field(..., min_length=10, max_length=4096)
    sid: str = Field(default="", max_length=4096)


class GroupServerExecutor(BaseModel):
    id: int
    persona_id: int
    display_name: str | None
    status: AccountStatus


class GroupServerItem(BaseModel):
    id: int
    server_id: int
    # 末次见到的 gameId，用来跳到服务器页；服务器没在线过时为空
    game_id: int | None
    name: str | None
    bound_by_name: str | None
    bound_via: Literal["owner", "admin"]
    executor: GroupServerExecutor | None
    # active：群成员在这台服上有权限；revoked：绑定人已不是服主或管理员，权限失效
    status: Literal["active", "revoked"]
    status_reason: str | None
    # 执行账号的问题（没指定、登录失败、不是管理员），不影响权限，但服管操作会失败
    executor_problem: str | None
    last_verified_at: datetime | None
    created_at: datetime


class GroupServerListResponse(BaseModel):
    items: list[GroupServerItem]


class GroupServerBindRequest(BaseModel):
    game_id: int = Field(..., gt=0)
    # 不填就按默认账号优先，挑第一个是这台服服主或管理员的
    account_id: int | None = None


class GroupServerExecutorRequest(BaseModel):
    account_id: int


class ServerGroupItem(BaseModel):
    group_id: int
    group_name: str
    bound_by_name: str | None
    bound_via: Literal["owner", "admin"]
    status: Literal["active", "revoked"]
    created_at: datetime


class ServerGroupListResponse(BaseModel):
    items: list[ServerGroupItem]


# ===== 群成员在玩状态（右侧好友栏） =====

PresenceSlot = Literal["team1", "team2", "queue", "spectator"]


class MemberServer(BaseModel):
    """成员所在的服。服务器摘要缓存里没有这台服时，只有 game_id 和 slot。"""

    game_id: int
    slot: PresenceSlot
    name: str | None = None
    map_display_name: str | None = None
    mode_display_name: str | None = None
    player_count: int | None = None
    max_player_count: int | None = None


class PresenceMemberItem(BaseModel):
    user_id: int
    username: str
    display_name: str | None
    avatar_url: str | None
    persona_id: int | None
    role: GroupRole
    # 不在任何有人的服里时为 null：可能离线，也可能停在主菜单
    server: MemberServer | None


class PresenceGroupItem(BaseModel):
    id: int
    name: str
    members: list[PresenceMemberItem]


class GroupPresenceResponse(BaseModel):
    # 最近一轮全服快照的时间；为 null 表示状态暂不可用（快照连续失败或缓存不可用）
    updated_at: datetime | None
    groups: list[PresenceGroupItem]
