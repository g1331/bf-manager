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


class RoundWeapon(BaseModel):
    """一个人在一局里用过的一件武器或载具：这一局的增量，没用到的指标为 0"""

    kind: Literal["weapon", "vehicle"]
    name: str | None = None
    category: str | None = None
    image: str | None = None
    kills: int = 0
    headshots: int = 0
    hits: int = 0
    shots: int = 0
    seconds: int = 0
    destroyed: int = 0
    # 击杀里含骑乘时用别的武器打的（战马），和武器重复，不能和其他条目相加
    shared_kills: bool = False
    # 这件武器载具在这一局之前的生涯水平（只在单局详情里有）：命中率、爆头率（爆头 ÷ 击杀）、KPM
    career_accuracy: float | None = None
    career_headshot_rate: float | None = None
    career_kpm: float | None = None


class RoundRibbon(BaseModel):
    """本局拿到的一种勋带：code 即图鉴 ribbons 的 code（r01…r47）"""

    code: str
    count: int


class RoundStar(BaseModel):
    """本局击杀跨过整百、拿到新服役星的武器载具"""

    kind: Literal["weapon", "vehicle"]
    name: str | None = None
    image: str | None = None
    stars: int  # 新的星数


class RoundScoreParts(BaseModel):
    """得分构成，加起来是总分 score。前四项是游戏内计分板上的分数，后两项是结算时另给的经验"""

    general: int  # 常规：击杀、伤害等
    team: int  # 团队：复活、补给、修理等
    squad: int  # 小队
    objective: int  # 本局模式的目标得分（占点、炸弹、信鸽……）
    other: int  # 总分减去各项后剩下的（载具、巨兽等），可能为负的零头
    award: int  # 勋带勋章奖励
    bonus: int  # 结算奖励，只有打到结算的人有


class RoundCareer(BaseModel):
    """这一局之前的生涯水平，和单局数字对比用。2026-11 前存的快照没有命中、爆头和得分构成，
    对应项为空；spm 和单局 spm 同口径（扣掉勋带勋章奖励和结算奖励）"""

    kd: float | None = None
    kpm: float | None = None
    spm: float | None = None
    accuracy: float | None = None
    headshot_rate: float | None = None


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
    # 按击杀、时长倒序；None 表示这一局没有武器载具数据（功能上线前，或当时没读到）
    weapons: list[RoundWeapon] | None = None
    # 以下来自 2026-11 起记录的统计，之前的对局为空 / 默认值
    # 和游戏内计分板同口径的分数：总分减去勋带勋章奖励和结算奖励；有它时 spm 按它算
    battle_score: int | None = None
    score_parts: RoundScoreParts | None = None
    mvp: bool = False
    ace_squad: bool = False
    # 次数多的在前；None 表示这一局没有勋带数据
    ribbons: list[RoundRibbon] | None = None
    medals: int = 0  # 本局完成的勋章
    # 只放非零项。objective 的键：flag_captures、flag_defends、bombs_placed、bombs_defused、
    # artillery_defense_kills、pigeons_delivered、pigeons_written、pigeon_carriers_killed、
    # resupplies、spot_assists、suppression_assists、squad_spawns、orders_completed、
    # squad_kill_assists；combat 的键：headshots、shots、hits、soldier_damage、vehicle_damage、
    # avenger_kills、savior_kills、nemesis_kills、squad_wipes、vehicles_destroyed
    objective: dict[str, int] = {}
    combat: dict[str, int] = {}
    rank_to: int | None = None  # 本局升级后的等级
    kit_ranks: list[str] = []  # 本局升级的兵种
    skill_delta: float | None = None  # 技巧值变化，没变或没有数据为空
    # 本局刷新的生涯纪录 → 新纪录：max_killstreak、longest_headshot（米）、max_nemesis_streak
    records: dict[str, int] = {}
    stars: list[RoundStar] = []
    # 这一局之前、加上这一局之后的生涯水平，只在单局详情里有；14 天没被跟踪到的人没有快照，为空
    career: RoundCareer | None = None
    career_after: RoundCareer | None = None


class RoundDetail(RoundSummary):
    players: list[RoundPlayer]
    # 游戏评出的本局 MVP 与王牌小队（只认打到结算的人），没有数据时为空
    mvp_pid: int | None = None
    ace_squad_pids: list[int] = []


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
