"""BF1 玩家相关 schema"""

from __future__ import annotations

from pydantic import BaseModel


class PersonaBrief(BaseModel):
    """persona 基本信息"""

    persona_id: int
    display_name: str
    avatar_url: str | None = None
    # BF1 生涯时长（小时，取整）。EA 允许多账号共用同一昵称，仅当搜索结果出现重名时为消歧
    # 回填——0 表示未玩过 BF1（空号，服管操作会报玩家不存在），>0 为真号；None 表示未查询。
    time_played_hours: int | None = None


class PersonaSearchResult(BaseModel):
    """按昵称搜索 persona 的返回"""

    query: str
    personas: list[PersonaBrief]
