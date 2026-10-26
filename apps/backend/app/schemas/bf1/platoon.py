"""BF1 战队 schema"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.bf1.server import ServerSummary
from app.schemas.bf1.stats import PlayerPlatoon

PlatoonRole = Literal["general", "colonel", "lieutenant", "private"]


class PlatoonMember(BaseModel):
    """战队成员。role 为空表示 EA 返回了未知职位"""

    persona_id: int
    name: str
    role: PlatoonRole | None = None
    avatar_url: str | None = None


class PlatoonServer(BaseModel):
    """战队成员正在玩的服务器，members 为其中的本队成员"""

    server: ServerSummary
    members: list[PlatoonMember] = []


class PlatoonDetail(PlayerPlatoon):
    """战队详情：基本信息 + 全部成员（按职位从高到低）+ 成员正在玩的服务器"""

    created_at: int | None = None  # unix 秒
    free_join: bool = False  # 无需审批直接加入
    can_apply: bool = False  # 可以申请加入
    members: list[PlatoonMember] = Field(default_factory=list)
    servers: list[PlatoonServer] = Field(default_factory=list)


class PlatoonSearchItem(BaseModel):
    guid: str
    tag: str | None = None
    name: str | None = None
    size: int | None = None
    emblem_url: str | None = None
