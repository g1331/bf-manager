"""平台运维统计的响应模型"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EndpointCount(BaseModel):
    """按接口分组累计的请求次数。group 形如 ``bf1/stats``、``bf1/servers``。"""

    group: str
    count: int = 0


class DailyCount(BaseModel):
    """单日请求量、去重活跃用户数与去重游客数（未登录，按 IP）。date 为 ``YYYY-MM-DD``。"""

    date: str
    requests: int = 0
    active_users: int = 0
    guests: int = 0
    ea_calls: int = 0


class EaSourceCount(BaseModel):
    """今天某个来源发给 EA 的请求数；pids 是其中 Stats.getStats 查询的人次（每批最多 STATS_BATCH_SIZE 人）。

    来源形如 ``tracker``、``tracker_probe``、``snapshot``、``api:bf1/stats``。
    """

    source: str
    calls: int = 0
    pids: int = 0


class EaMethodCount(BaseModel):
    """今天按「通道、方法、来源」细分的 EA 请求数。通道为 blaze / gateway / accounts / sal。"""

    channel: str
    method: str
    source: str
    count: int = 0


class EaHourCount(BaseModel):
    """某个整点小时（UTC，ISO 格式）内的 EA 请求总数。"""

    hour: str
    count: int = 0


class TrackerEventCount(BaseModel):
    """今天对局跟踪器的一类事件计数，name 如 want_join、join_hop、recheck_changed_fresh。"""

    name: str
    count: int = 0


class AdminMetrics(BaseModel):
    """平台访问运维快照。available=False 表示缓存层不可用，统计暂不可读。"""

    available: bool = False
    total_requests: int = 0
    requests_today: int = 0
    requests_7d: int = 0
    active_users_today: int = 0
    active_users_7d: int = 0
    guests_today: int = 0
    guests_7d: int = 0
    top_endpoints: list[EndpointCount] = Field(default_factory=list)
    # 最近 7 天，按日期升序排列，便于前端从左到右画趋势
    daily: list[DailyCount] = Field(default_factory=list)
    # 发给 EA 的请求（Blaze、Gateway 等），按来源和方法拆开
    ea_calls_today: int = 0
    ea_calls_7d: int = 0
    ea_sources: list[EaSourceCount] = Field(default_factory=list)
    ea_methods: list[EaMethodCount] = Field(default_factory=list)
    # 最近 24 小时，按小时升序
    ea_hourly: list[EaHourCount] = Field(default_factory=list)
    # 今天对局跟踪器各环节的人数，按名字排序
    tracker_events: list[TrackerEventCount] = Field(default_factory=list)
