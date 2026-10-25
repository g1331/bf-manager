"""BF1 行动服自动换图 schema"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AutoSwitchItem(BaseModel):
    """编排的一项。operation：从这张图开始打完整个战役算一次；map：打完这一张图算一次"""

    map: str = Field(..., max_length=64)
    scope: Literal["operation", "map"]
    repeat: int = Field(1, ge=1, le=9)


class AutoSwitchPlan(BaseModel):
    items: list[AutoSwitchItem] = Field(default_factory=list, max_length=50)
    loops: int = Field(0, ge=0, le=99)  # 整轮循环次数，0 为一直循环


class AutoSwitchEvent(BaseModel):
    ts: float
    kind: str
    message: str


class AutoSwitchView(BaseModel):
    enabled: bool = False
    plan: AutoSwitchPlan = AutoSwitchPlan()
    cursor: int = 0  # 正在进行的编排项下标
    done: int = 0  # 当前项已打完的次数
    loop: int = 1  # 当前第几轮
    pending_map: str | None = None  # 已发出换图、还没落到的目标图
    enabled_by: str | None = None  # 开启人的平台用户名
    enabled_at: float | None = None
    events: list[AutoSwitchEvent] = []
