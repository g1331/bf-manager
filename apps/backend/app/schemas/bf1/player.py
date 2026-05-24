"""BF1 玩家相关 schema"""

from __future__ import annotations

from pydantic import BaseModel


class PersonaBrief(BaseModel):
    """persona 基本信息"""

    persona_id: int
    display_name: str
    avatar_url: str | None = None


class PersonaSearchResult(BaseModel):
    """按昵称搜索 persona 的返回"""

    query: str
    personas: list[PersonaBrief]
