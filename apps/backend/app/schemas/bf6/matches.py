"""BF6 对局估算 schema。

每条是同一玩家两次读取生涯之间的增量，不是 EA 的逐场战报：间隔内打了几场就合并成几场，
时间是读到变化的时刻，不是开局或结算时间。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.bf6.catalog import Bf6NamedItem


class Bf6MatchSplit(Bf6NamedItem):
    """这段里某个模式或地图打了几场、赢输各几场。"""

    matches: int
    wins: int
    losses: int


class Bf6MatchItem(Bf6NamedItem):
    """这段里用过的武器或载具。"""

    kills: int
    time_seconds: int


class Bf6MatchDelta(BaseModel):
    """两次快照之间的差值，存进 bf6_match_estimates.payload。"""

    matches: int
    wins: int
    losses: int
    modes: list[Bf6MatchSplit]
    maps: list[Bf6MatchSplit]
    # 口径同生涯：kills 含 AI，K/D、KPM 用 human_kills
    kills: int
    human_kills: int
    deaths: int
    score: int
    time_seconds: int
    damage: int
    assists: int
    revives: int
    headshots: int
    xp: int
    # 战斗时间最长的兵种
    kit: str | None
    weapons: list[Bf6MatchItem]
    vehicles: list[Bf6MatchItem]
    kd: float | None
    kpm: float | None


class Bf6MatchEstimate(Bf6MatchDelta):
    id: int
    kit_name: str | None = None
    # 这段的对局在 started_after 之后结束，observed_at 时读到
    started_after: datetime
    observed_at: datetime


class Bf6MatchList(BaseModel):
    # 是否在记录这名玩家；为假时说明还没人查过，或太久没人查已停止
    tracking: bool
    tracked_since: datetime | None
    last_checked_at: datetime | None
    matches: list[Bf6MatchEstimate]
