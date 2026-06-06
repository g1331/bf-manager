"""平台运维统计的响应模型"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EndpointCount(BaseModel):
    """按接口分组累计的请求次数。group 形如 ``bf1/stats``、``bf1/servers``。"""

    group: str
    count: int = 0


class DailyCount(BaseModel):
    """单日请求量与去重活跃用户数。date 为 ``YYYY-MM-DD``。"""

    date: str
    requests: int = 0
    active_users: int = 0


class AdminMetrics(BaseModel):
    """平台访问运维快照。available=False 表示缓存层不可用，统计暂不可读。"""

    available: bool = False
    total_requests: int = 0
    requests_today: int = 0
    requests_7d: int = 0
    active_users_today: int = 0
    active_users_7d: int = 0
    top_endpoints: list[EndpointCount] = Field(default_factory=list)
    # 最近 7 天，按日期升序排列，便于前端从左到右画趋势
    daily: list[DailyCount] = Field(default_factory=list)
