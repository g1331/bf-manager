"""ServerMembership 请求 / 响应 schema"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

MembershipRole = Literal["viewer", "moderator", "admin", "owner"]


class MembershipItem(BaseModel):
    id: int
    user_id: int
    user_persona_id: int
    user_display_name: str | None
    server_pk: int
    game: str
    server_id: int
    server_name: str | None
    role: MembershipRole
    granted_by: int | None
    granted_at: datetime


class MembershipPage(BaseModel):
    items: list[MembershipItem]
    total: int


class MembershipUpsertRequest(BaseModel):
    """按 (persona_id, game, server_id) 找或建 user / server，写入或更新 role"""

    target_persona_id: int = Field(..., gt=0, description="被授予权限的玩家 persona_id")
    game: str = Field(..., min_length=1, max_length=16)
    server_id: int = Field(..., gt=0, description="EA serverId")
    role: MembershipRole
