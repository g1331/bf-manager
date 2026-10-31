"""BF1 一键卡行动 schema"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CardCredentials(BaseModel):
    """服主或管理员的凭据：匿名填 remid + sid；登录用户可改用主绑定账号（use_binding）"""

    remid: str = Field("", max_length=2048)
    sid: str = Field("", max_length=2048)
    use_binding: bool = False


class CardPrecheckRequest(CardCredentials):
    game_id: int = Field(..., gt=0)


class CardStartRequest(CardPrecheckRequest):
    kind: Literal["card", "anchor"] = "card"


class CardRestoreRequest(CardCredentials):
    pass


class CardPrecheck(BaseModel):
    game_id: int
    server_id: int
    server_name: str
    persona_id: int  # 凭据对应的 EA 账号
    owner_id: int
    owner_name: str
    is_owner: bool
    is_admin: bool  # 在 rspInfo.adminList 里；服主或管理员都能卡行动
    occupied: int  # 士兵 + 观战 + 排队
    soldier_max: int
    mode: str
    map_name: str
    map_count: int
    is_operation: bool  # 已经是 24 图行动
    auto_switch_enabled: bool
    running_job_id: int | None = None


class CardEvent(BaseModel):
    ts: float
    kind: str  # info / round / warn / error / success
    message: str


class CardJobView(BaseModel):
    id: int
    kind: str
    game_id: int
    server_name: str
    persona_id: int
    persona_name: str
    status: Literal["running", "succeeded", "failed", "cancelled", "interrupted"]
    attempts: int
    max_attempts: int
    message: str
    result_maps: list[str] | None = None
    can_restore: bool
    restored_at: float | None = None
    started_at: float
    finished_at: float | None = None
    events: list[CardEvent] = []


class CardStartResult(BaseModel):
    job: CardJobView
    # 查看 / 停止 / 恢复这个任务的凭证，只返回这一次
    token: str
