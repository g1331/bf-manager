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


class MovePlayerRequest(BaseModel):
    """换边请求。team_id 是玩家「当前所在队伍」的 Blaze TIDX（0 或 1），后端据此把他
    换到对面阵营——换边总是 toggle，不存在指定目标队伍，因此请求体只需当前队伍号。
    """

    persona_id: int
    team_id: int = Field(..., ge=0, le=1)


class AdminActionResult(BaseModel):
    success: bool
    message: str | None = None


class MyServerRoleResult(BaseModel):
    """当前登录用户对某服务器的角色，供前端按角色 gating 内联服管操作。"""

    role: str | None = None
    is_platform_admin: bool = False
