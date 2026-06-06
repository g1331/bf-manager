"""BF1 服管操作 schema"""

from __future__ import annotations

from pydantic import BaseModel, Field


class KickPlayerRequest(BaseModel):
    persona_id: int
    reason: str = Field(default="kicked by admin", max_length=128)


class BanPlayerRequest(BaseModel):
    persona_id: int


class ServerMemberRequest(BaseModel):
    """VIP / 管理员名单的增减请求，仅需目标 persona。"""

    persona_id: int


class ChooseLevelRequest(BaseModel):
    """换图请求。换图目标由后端依授权服务器自身记录派生，请求体仅需地图序号。"""

    level_index: int = Field(..., ge=0, le=100)


class AdminActionResult(BaseModel):
    success: bool
    message: str | None = None
