"""BF1 服管操作 schema"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class KickPlayerRequest(BaseModel):
    persona_id: int
    reason: str = Field(default="kicked by admin", max_length=128)


class BanPlayerRequest(BaseModel):
    persona_id: int


class ServerMemberRequest(BaseModel):
    """VIP / 管理员名单的增减请求，仅需目标 persona。"""

    persona_id: int


class VipGrantRequest(BaseModel):
    """加 V / 改期。days 为空表示永久；可以为负，用来缩短期限。

    display_name 只用于记录展示（不在 EA 名单里的排队玩家拿不到名字），不参与寻址。
    给永久 VIP 设天数会把它改成限时，须显式带 allow_permanent_to_timed。
    """

    persona_id: int
    days: int | None = Field(default=None, ge=-3650, le=3650)
    display_name: str | None = Field(default=None, max_length=64)
    allow_permanent_to_timed: bool = False


class TimedVipItem(BaseModel):
    persona_id: int
    display_name: str | None = None
    # active：已在 EA 名单里；pending：行动服待生效队列
    status: Literal["active", "pending"]
    expires_at: datetime | None = None
    # 剩余秒数：active 是距到期（查询时算），pending 是冻结的剩余时长；为空表示永久
    remaining_seconds: int | None = None
    # 已到期但还没下掉（行动服等 checkvip，或普通服自动下 V 失败）
    expired: bool = False
    queue_position: int | None = None
    last_error: str | None = None


class TimedVipView(BaseModel):
    """VIP 页的托管信息：EA 名单人数、行动服状态与平台托管的记录。"""

    operation: bool
    map_name: str | None = None
    # 当前图是不是战役第一张（重开它不丢战役进度）
    campaign_start: bool = False
    players: int = 0
    # EA 名单里的全部 persona，用来区分永久 VIP（在名单里但没有托管记录）
    vip_ids: list[int]
    capacity: int
    queue_limit: int
    items: list[TimedVipItem]


class VipApplyRequest(BaseModel):
    """checkvip：先下掉过期的再按顺序补空位；restart 为真时有变动就重开当前地图。"""

    restart: bool = False


class VipApplyFailure(BaseModel):
    persona_id: int
    display_name: str | None = None
    action: Literal["add", "remove", "restart"]
    message: str


class VipApplyResult(BaseModel):
    message: str
    removed: int
    added: int
    waiting: int
    restarted: bool = False
    failures: list[VipApplyFailure] = []


class ChooseLevelRequest(BaseModel):
    """换图请求。换图目标由服务端按 game_id 向 EA 实时解析，请求体仅需地图序号。"""

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


class MyServerItem(BaseModel):
    """「我的服务器」列表项：当前用户有服管角色的一台服务器。

    game_id 为末次解析到的 EA gameId（详情页据此寻址），可能为空（尚未在线时识别）或已过期
    （服务器重启后变化），前端据此决定链接是否可点。
    """

    server_pk: int
    game: str
    server_id: int
    game_id: int | None = None
    name: str | None = None
    role: str
    # 经由群组获得的权限：群名（同一台服挂在多个群里时取第一个）；EA 识别或人工授权的为空
    via_group: str | None = None


class MyServersResponse(BaseModel):
    items: list[MyServerItem]
