"""BF1 全服统计聚合的响应模型"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CountBreakdown(BaseModel):
    """同一指标在不同维度上的拆分。

    用于服务器数、在线人数、排队人数、观众人数四类指标，各自按官方/私服与
    亚洲/欧洲/其他地区拆分。
    """

    total: int = 0
    official: int = 0
    private: int = 0
    asia: int = 0
    eu: int = 0
    other: int = 0


class NamedCount(BaseModel):
    """按地图模式或游戏模式分组后的服务器数与在线人数。"""

    label: str
    servers: int = 0
    players: int = 0


class BF1Overview(BaseModel):
    """BF1 全服统计快照。available=False 表示后台尚未拉到有效数据。"""

    available: bool = False
    updated_at: str | None = None
    # 本轮成功的并发拉取次数与去重前的原始记录数，用于判断采样是否充分
    sample_pulls: int = 0
    raw_count: int = 0

    servers: CountBreakdown = Field(default_factory=CountBreakdown)
    players: CountBreakdown = Field(default_factory=CountBreakdown)
    queues: CountBreakdown = Field(default_factory=CountBreakdown)
    spectators: CountBreakdown = Field(default_factory=CountBreakdown)

    top_map_modes: list[NamedCount] = Field(default_factory=list)
    mode_distribution: list[NamedCount] = Field(default_factory=list)
