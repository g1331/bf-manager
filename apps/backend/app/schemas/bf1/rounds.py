"""BF1 对局 schema：由生涯差分算出的每局战绩"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class RoundSummary(BaseModel):
    """一局的概要，时间为 unix 秒"""

    id: int
    game_id: int
    # 这台服现在的 gameId：重启后换新，旧 gameId 打不开服务器详情，跳转用这个
    server_game_id: int
    server_name: str | None = None
    map_name: str | None = None
    map_display_name: str | None = None
    map_image_url: str | None = None
    game_mode: str | None = None
    mode_display_name: str | None = None
    started_at: int
    ended_at: int
    # 开局时就在跟踪；为假时开始时间是接手的时刻，开局后很快退出的人可能不全
    observed_start: bool
    # 看到了结算；为假时服务器中途关掉或采集断档，这一局没打完
    settled: bool
    winner: Literal[1, 2] | None = None
    team1_faction: str | None = None
    team2_faction: str | None = None
    player_count: int


class RoundPlayer(BaseModel):
    """一个人在一局里的战绩。秒数是各兵种在场秒数之和，kd / kpm / spm 都按它算"""

    persona_id: int
    name: str | None = None
    team: Literal[1, 2]
    # finished 打到结算；left 中途退出，没有胜负；suspect 增量里混了别的局，仅供参考
    status: Literal["finished", "left", "suspect"]
    won: bool | None = None
    kills: int
    deaths: int
    score: int
    assists: int
    revives: int
    heals: int
    repairs: int
    dogtags: int
    vehicle_kills: int
    seconds: int
    kit: str | None = None  # 在场最久的兵种（assault / medic / ... / elite）
    kd: float | None = None
    kpm: float | None = None
    spm: float | None = None


class RoundDetail(RoundSummary):
    players: list[RoundPlayer]


class RoundPage(BaseModel):
    items: list[RoundSummary]
    # 下一页传给 before；为空表示没有更早的了
    next_before: int | None = None


class PlayerRound(BaseModel):
    round: RoundSummary
    player: RoundPlayer


class PlayerRoundPage(BaseModel):
    items: list[PlayerRound]
    # 下一页传给 before（对局 id）；为空表示没有更早的了
    next_before: int | None = None
