"""BF1 Blaze 服务：拉取服务器实时玩家列表

Blaze 是 EA 后端的二进制长连接协议，提供 Gateway 拿不到的房间实时名单（队伍 / 延迟 /
等级 / 语言）。本模块在协议层（``domain.ea.blaze_protocol``）之上做三件事：

1. 维护一个进程级 Blaze 连接池：单 worker 部署下复用同一条已登录连接，按连接年龄上限
   主动重建，避免每次查询都付出建连 + TLS + 登录的冷启动成本。
2. 封装 Blaze 登录序列：用账号池凭据取 Blaze authcode，经 redirector 拿到 Blaze 服务器
   地址，建立加密连接并完成 ``Authentication.login``。
3. 组装玩家列表：Blaze roster 叠加 ATTR 里的管理 / VIP 名单、平台已绑定用户标记，以及可选的
   生涯战绩（并发限流合并）。

连接池为进程级单例，``close_blaze_pool`` 在 FastAPI lifespan 关闭时调用。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import EAApiError, NotFoundError
from app.core.cache import Cache, get_cache
from app.core.config import get_settings
from app.domain.ea.account_pool import EACredentials
from app.domain.ea.blaze_protocol.socket import BlazeServerREQ, BlazeSocket
from app.domain.ea.data_handle import BlazeData
from app.domain.games.bf1.maps import OPERATION_SECTORS, MapData
from app.models.ea_binding import EaBinding
from app.schemas.bf1.server import (
    BlazePlayer,
    BlazePlayerStats,
    BlazeTeamGroup,
    OperationProgress,
    ServerPlayersResponse,
    ServerPlayersSummary,
)
from app.services.bf1.gateway_factory import get_bf1_client
from app.services.bf1.server_service import operation_map_list
from app.services.ea_account_service import EAAccountService

# Blaze 单条连接的最大存活时间（秒）。超龄主动重建，规避 EA 端静默断开后我方仍误判可用。
CONNECTION_MAX_AGE_SECONDS = 300
# 单次 Blaze 查询（含大体量 roster 解码）的超时。
BLAZE_QUERY_TIMEOUT = 20
# 并发查询生涯战绩的上限，控制对 EA Gateway 的瞬时压力，避免触发限流。
STATS_CONCURRENCY = 8
# 生涯战绩按 personaId 缓存的时长（秒）。生涯数据几分钟内几乎不变，刷新同一服务器时
# 大部分玩家直接命中缓存，不再逐个打 EA。
STATS_CACHE_TTL_SECONDS = 600
STATS_CACHE_PREFIX = "bf1:basic_stats"
# 只缓存计算胜率 / KD / KPM / 时长 / 估算等级所需的字段。
_CACHED_BASIC_FIELDS = ("kills", "deaths", "wins", "losses", "timePlayed", "kpm", "spm")
# BF1 满级。
RANK_MAX = 150
# Blaze TIDX 中表示「排队 / 旁观」而非真实队伍的哨兵值。
TEAM_SENTINEL = 65535
# 全服快照从发请求到收齐推送的总超时（实测约 2s）。
GAME_LIST_SNAPSHOT_TIMEOUT = 18

_MOCK_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "domain"
    / "ea"
    / "blaze_protocol"
    / "fixtures"
    / "server_players_mock.json"
)


class _BlazeConnectionPool:
    """进程级 Blaze 连接池（单 worker asyncio 部署下安全）。

    采用 sticky 账号策略：首次从账号池取一个可用账号作为 Blaze 专用账号并缓存其凭据，
    后续所有查询复用同一条连接。连接超龄或鉴权失效时重建；账号本身失效时清空 sticky
    凭据，下次从池中换号。``_lock`` 串行化建连 / 重建，避免并发查询同时触发重连竞态。
    """

    def __init__(self) -> None:
        self._socket: BlazeSocket | None = None
        self._created_at: float = 0.0
        self._creds: EACredentials | None = None
        self._lock = asyncio.Lock()

    async def get_socket(self, db: AsyncSession) -> BlazeSocket:
        async with self._lock:
            socket = self._socket
            if (
                socket is not None
                and socket.connect
                and getattr(socket, "authenticated", False)
                and time.monotonic() - self._created_at < CONNECTION_MAX_AGE_SECONDS
            ):
                return socket

            await self._close_locked()

            if self._creds is None:
                self._creds = await EAAccountService(db).pick_available()

            try:
                new_socket = await self._connect_and_login(self._creds)
            except Exception:
                # 建连或登录失败可能是该账号凭据失效，清空 sticky 凭据使下次换号重试。
                self._creds = None
                raise

            self._socket = new_socket
            self._created_at = time.monotonic()
            return new_socket

    async def _connect_and_login(self, creds: EACredentials) -> BlazeSocket:
        auth_code = await _fetch_blaze_authcode(creds)
        host, port = await BlazeServerREQ.get_server_address()
        socket = await BlazeSocket.create(host, port)
        login_packet = {
            "method": "Authentication.login",
            "type": "Command",
            "id": 0,
            "length": 28,
            "data": {"AUTH 1": auth_code, "EXTB 2": "", "EXTI 0": 0},
        }
        try:
            response = await socket.send(login_packet, timeout=BLAZE_QUERY_TIMEOUT)
        except Exception as exc:
            with contextlib.suppress(Exception):
                await socket.close()
            raise EAApiError(
                code="BLAZE_LOGIN_FAILED",
                message=f"Blaze 登录失败: {exc}",
            ) from exc
        if not isinstance(response, dict) or response.get("type") == "Error":
            with contextlib.suppress(Exception):
                await socket.close()
            raise EAApiError(
                code="BLAZE_LOGIN_FAILED",
                message=f"Blaze 登录返回异常: {response}",
            )
        socket.authenticated = True
        name = ((response.get("data", {}).get("SESS") or {}).get("PDTL") or {}).get("DSNM")
        logger.success(f"Blaze 登录成功，账号 {creds.persona_id}（{name}）")
        return socket

    async def _close_locked(self) -> None:
        if self._socket is not None:
            with contextlib.suppress(Exception):
                await self._socket.close()
            self._socket = None

    async def close_all(self) -> None:
        async with self._lock:
            await self._close_locked()
            self._creds = None

    async def invalidate(self) -> None:
        """标记当前连接失效（查询期间网络异常时调用），下次查询触发重建。"""
        async with self._lock:
            await self._close_locked()


_pool = _BlazeConnectionPool()
# 快照经 socket.callback 收推送，同一时间只能有一个快照占用回调。
_snapshot_lock = asyncio.Lock()


async def close_blaze_pool() -> None:
    """FastAPI lifespan 关闭时调用，释放 Blaze 长连接。"""
    await _pool.close_all()


async def _fetch_blaze_authcode(creds: EACredentials) -> str:
    """用账号池凭据换取一次性 Blaze authcode。

    临时构造 ``BF1GatewayClient`` 仅为复用其 ``getBlazeAuthcode``，取到后立即关闭其
    HTTP session。失败时 ``getBlazeAuthcode`` 会返回响应正文字符串而非短 authcode，
    这里据此判失败。
    """
    from app.domain.games.bf1.gateway import BF1GatewayClient  # noqa: PLC0415

    async def _noop(*_args: object, **_kwargs: object) -> None:
        return None

    client = BF1GatewayClient(
        pid=creds.persona_id,
        remid=creds.remid,
        sid=creds.sid,
        session=creds.session,
        on_session_refreshed=_noop,
    )
    try:
        code = await client.getBlazeAuthcode()
    finally:
        with contextlib.suppress(Exception):
            http_session = getattr(client, "http_session", None)
            if http_session is not None:
                await http_session.close()

    # 合法 authcode 是不含空白的短 token；失败时返回的是 HTML/JSON 正文。
    if not isinstance(code, str) or not code or len(code) > 256 or any(c.isspace() for c in code):
        raise EAApiError(
            code="BLAZE_AUTHCODE_FAILED",
            message=f"获取 Blaze authcode 失败: {str(code)[:200]}",
        )
    return code


# BF1 各等级的累计经验阈值（下标即等级，0..150）。Blaze roster 与 detailedStats 的
# basicStats 多数情况下不返回 rank（为 null），需用「击杀分速 spm × 游玩时长 / 60」估出
# 累计经验再查此表反推等级，否则列表会大面积显示等级 0。
RANK_EXP_THRESHOLDS: tuple[int, ...] = (
    0,
    1000,
    5000,
    15000,
    25000,
    40000,
    55000,
    75000,
    95000,
    120000,
    145000,
    175000,
    205000,
    235000,
    265000,
    295000,
    325000,
    355000,
    395000,
    435000,
    475000,
    515000,
    555000,
    595000,
    635000,
    675000,
    715000,
    755000,
    795000,
    845000,
    895000,
    945000,
    995000,
    1045000,
    1095000,
    1145000,
    1195000,
    1245000,
    1295000,
    1345000,
    1405000,
    1465000,
    1525000,
    1585000,
    1645000,
    1705000,
    1765000,
    1825000,
    1885000,
    1945000,
    2015000,
    2085000,
    2155000,
    2225000,
    2295000,
    2365000,
    2435000,
    2505000,
    2575000,
    2645000,
    2745000,
    2845000,
    2945000,
    3045000,
    3145000,
    3245000,
    3345000,
    3445000,
    3545000,
    3645000,
    3750000,
    3870000,
    4000000,
    4140000,
    4290000,
    4450000,
    4630000,
    4830000,
    5040000,
    5260000,
    5510000,
    5780000,
    6070000,
    6390000,
    6730000,
    7110000,
    7510000,
    7960000,
    8430000,
    8960000,
    9520000,
    10130000,
    10800000,
    11530000,
    12310000,
    13170000,
    14090000,
    15100000,
    16190000,
    17380000,
    20000000,
    20500000,
    21000000,
    21500000,
    22000000,
    22500000,
    23000000,
    23500000,
    24000000,
    24500000,
    25000000,
    25500000,
    26000000,
    26500000,
    27000000,
    27500000,
    28000000,
    28500000,
    29000000,
    29500000,
    30000000,
    30500000,
    31000000,
    31500000,
    32000000,
    32500000,
    33000000,
    33500000,
    34000000,
    34500000,
    35000000,
    35500000,
    36000000,
    36500000,
    37000000,
    37500000,
    38000000,
    38500000,
    39000000,
    39500000,
    40000000,
    41000000,
    42000000,
    43000000,
    44000000,
    45000000,
    46000000,
    47000000,
    48000000,
    49000000,
    50000000,
)


def _rank_from_basic(basic: dict) -> int | None:
    """由 basicStats 的 spm 与 timePlayed 估算累计经验，查表反推等级。

    roster / basicStats 的 rank 字段多为 null，故用经验值估算补齐：
    ``exp = spm * timePlayed / 60``，再在 ``RANK_EXP_THRESHOLDS`` 中取首个不小于 exp 的
    阈值下标减一作为等级。spm 或时长缺失时返回 None，由调用方回退 roster 给的等级。
    """
    try:
        spm = float(basic.get("spm") or 0)
        time_played = float(basic.get("timePlayed") or 0)
    except (TypeError, ValueError):
        return None
    if spm <= 0 or time_played <= 0:
        return None
    exp = spm * time_played / 60
    if exp <= RANK_EXP_THRESHOLDS[1]:
        return 0
    if exp >= RANK_EXP_THRESHOLDS[-1]:
        return RANK_MAX
    for level in range(1, len(RANK_EXP_THRESHOLDS)):
        if exp <= RANK_EXP_THRESHOLDS[level]:
            return level - 1
    return RANK_MAX


def _stats_from_basic(basic: dict) -> BlazePlayerStats:
    """从 detailedStats 的 basicStats 子字典提取列表所需的四项综合战绩。"""

    def _num(value: object) -> float:
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.0

    kills = _num(basic.get("kills"))
    deaths = _num(basic.get("deaths"))
    wins = _num(basic.get("wins"))
    losses = _num(basic.get("losses"))
    time_played = _num(basic.get("timePlayed"))
    kpm = basic.get("kpm")
    total_rounds = wins + losses
    return BlazePlayerStats(
        win_rate=(wins / total_rounds * 100) if total_rounds > 0 else None,
        kd=(kills / deaths) if deaths > 0 else None,
        kpm=_num(kpm) if kpm else None,
        time_hours=(time_played / 3600) if time_played else None,
    )


async def _stats_cache() -> Cache | None:
    try:
        return await get_cache()
    except Exception as exc:
        logger.warning(f"战绩缓存不可用，直接查询 EA: {exc}")
        return None


async def _cache_get(cache: Cache | None, pid: int) -> dict[str, Any] | None:
    if cache is None:
        return None
    try:
        cached = await cache.get(f"{STATS_CACHE_PREFIX}:{pid}")
    except Exception as exc:
        logger.warning(f"玩家 {pid} 战绩缓存读取失败: {exc}")
        return None
    return cached if isinstance(cached, dict) else None


async def _cache_set(cache: Cache | None, pid: int, basic: dict[str, Any]) -> None:
    if cache is None:
        return
    try:
        await cache.set(f"{STATS_CACHE_PREFIX}:{pid}", basic, ttl=STATS_CACHE_TTL_SECONDS)
    except Exception as exc:
        logger.warning(f"玩家 {pid} 战绩缓存写入失败: {exc}")


async def _gather_stats(
    client: object, pids: list[int]
) -> tuple[dict[int, BlazePlayerStats], dict[int, int]]:
    """并发查询多名玩家的生涯战绩，信号量限流，单个失败降级为无战绩。

    返回两张表：综合战绩 ``stats_map`` 与由经验值估算的等级 ``rank_map``。后者用于补齐
    roster 未给的等级，避免列表大面积显示等级 0。
    """
    if not pids:
        return {}, {}
    semaphore = asyncio.Semaphore(STATS_CONCURRENCY)
    cache = await _stats_cache()

    async def _one(pid: int) -> tuple[int, BlazePlayerStats | None, int | None]:
        basic = await _cache_get(cache, pid)
        if basic is None:
            async with semaphore:
                try:
                    res = await client.detailedStatsByPersonaId(pid)  # type: ignore[attr-defined]
                except Exception as exc:
                    logger.warning(f"玩家 {pid} 战绩查询失败，降级为无战绩: {exc}")
                    return pid, None, None
            if not isinstance(res, dict):
                return pid, None, None
            basic = (res.get("result") or {}).get("basicStats") or {}
            if not basic:
                return pid, None, None
            basic = {k: basic.get(k) for k in _CACHED_BASIC_FIELDS}
            await _cache_set(cache, pid, basic)
        return pid, _stats_from_basic(basic), _rank_from_basic(basic)

    results = await asyncio.gather(*[_one(pid) for pid in pids])
    stats_map = {pid: stats for pid, stats, _ in results if stats is not None}
    rank_map = {pid: rank for pid, _, rank in results if rank is not None}
    return stats_map, rank_map


def _attr_ids(attrs: dict[str, Any], key: str) -> set[int]:
    """解析 Blaze ATTR 里的 PID 名单（如 admins / vips）。

    长串按长度切成 ``key1``…``key4``，切口可能落在数字中间，须按序拼接后再按 ``;`` 拆分。
    名单与 Gateway rspInfo.adminList / vipList 一致，服主不在 admins 内。
    """
    joined = "".join(attrs.get(f"{key}{i}") or "" for i in range(1, 5))
    return {int(pid) for pid in joined.split(";") if pid.strip().isdigit()}


async def _fetch_registered_ids(db: AsyncSession, pids: Iterable[int]) -> set[int]:
    """查询哪些在线玩家已在本平台绑定 EA 账号（群版 UI「群友」高亮的本地映射）。"""
    pid_list = list({int(pid) for pid in pids})
    if not pid_list:
        return set()
    rows = await db.scalars(select(EaBinding.persona_id).where(EaBinding.persona_id.in_(pid_list)))
    return set(rows.all())


def _build_player(
    raw_player: dict,
    *,
    admin_ids: set[int],
    vip_ids: set[int],
    registered_ids: set[int],
    stats_map: dict[int, BlazePlayerStats],
    rank_map: dict[int, int],
) -> BlazePlayer:
    pid = int(raw_player["pid"])
    # roster 多数情况下不给等级，优先用战绩经验值估算出的等级，估算缺失时再回退 roster 值。
    rank = rank_map.get(pid)
    if rank is None:
        rank = int(raw_player.get("rank") or 0)
    return BlazePlayer(
        persona_id=pid,
        display_name=raw_player.get("display_name") or "",
        rank=rank,
        team=int(raw_player.get("team") if raw_player.get("team") is not None else TEAM_SENTINEL),
        latency=int(raw_player.get("latency") or 0),
        language=raw_player.get("language"),
        join_time=raw_player.get("join_time"),
        role=raw_player.get("role") or "normal",
        is_admin=pid in admin_ids,
        is_vip=pid in vip_ids,
        is_registered=pid in registered_ids,
        stats=stats_map.get(pid),
    )


def _faction_map(map_name: str | None) -> dict[int, str]:
    """从服务器当前地图查 BF1 阵营对阵表，得出 {team_id: 阵营名}。

    BF1 的对阵阵营（法国 / 德意志帝国等）由当前地图固定决定，用 Blaze ATTR ``level``
    （与 Gateway ``serverInfo.mapName`` 同格式）查 ``MapData.MapTeamDict``：
    Blaze TIDX 0 对应该图 Team1，TIDX 1 对应 Team2。未知地图返回空映射，前端回退「队伍 N」。
    """
    entry = MapData.MapTeamDict.get(map_name) if map_name else None
    if not entry:
        return {}
    return {0: entry["Team1"], 1: entry["Team2"]}


def _operation_progress(attrs: dict[str, Any]) -> OperationProgress | None:
    """行动模式服务器的当前进度；非行动模式或 ATTR 缺字段时返回 None。

    ATTR progress 是本图进度折成的 0-5 六档：floor(已拿下区域数 × 5 / 本图区域数)。官服实测
    3 区的图出现 1、3、5，4 区的图出现 0、1、2、3、5，5 区的图 0-5 都有。这里反推区域数；
    shortcut: 6 区的格拉巴山拿下第 1 区前后都是 0，会少算一区，EA 不给原始值无法区分。
    """
    level = attrs.get("level")
    progress = str(attrs.get("progress", ""))
    if attrs.get("mode") != "BreakthroughLarge" or not level or not progress.isdigit():
        return None
    maps = operation_map_list(level)
    sectors = OPERATION_SECTORS.get(level)
    taken = int(progress)
    teams = MapData.MapTeamDict.get(level) or {}
    return OperationProgress(
        maps=maps,
        map_index=[m.map_name for m in maps].index(level),
        sectors_taken=math.ceil(taken * sectors / 5) if sectors else taken,
        state=attrs.get("operationstate"),
        attacker=teams.get("Team1"),
        defender=teams.get("Team2"),
    )


def _build_team_groups(
    players: list[BlazePlayer], faction_by_team: dict[int, str]
) -> list[BlazeTeamGroup]:
    """把对战双方（Blaze TIDX 0/1）的在场玩家分成两队，每队内部按等级降序排列。

    仅 TIDX 0/1 为对阵两队；过渡态或未定队位（如 65534、65535 哨兵）的在场玩家无法
    归入任一阵营，不单独成列。
    """
    by_team: dict[int, list[BlazePlayer]] = {}
    for player in players:
        if player.team not in (0, 1):
            continue
        by_team.setdefault(player.team, []).append(player)
    groups: list[BlazeTeamGroup] = []
    for team_id in sorted(by_team):
        members = sorted(by_team[team_id], key=lambda m: m.rank, reverse=True)
        ranks = [m.rank for m in members if m.rank > 0]
        groups.append(
            BlazeTeamGroup(
                team_id=team_id,
                faction=faction_by_team.get(team_id),
                players=members,
                count=len(members),
                rank_150_count=sum(1 for m in members if m.rank >= RANK_MAX),
                avg_rank=(sum(ranks) / len(ranks)) if ranks else None,
            )
        )
    return groups


def _load_mock(game_id: int) -> ServerPlayersResponse:
    data = json.loads(_MOCK_FIXTURE.read_text(encoding="utf-8"))
    response = ServerPlayersResponse.model_validate(data)
    response.game_id = int(game_id)
    response.is_mock = True
    return response


async def get_server_players(
    db: AsyncSession,
    game_id: int,
    *,
    include_stats: bool = True,
) -> ServerPlayersResponse:
    """获取服务器实时玩家列表。

    开启 ``blaze_mock_mode`` 时直接返回内置 fixture，供本地无凭据预览前端效果。
    """
    if get_settings().blaze_mock_mode:
        return _load_mock(game_id)

    # 1. Blaze roster（长连接，纯网络，不触碰数据库）。
    socket = await _pool.get_socket(db)
    packet = {
        "method": "GameManager.getGameDataFromId",
        "type": "Command",
        "data": {
            "DNAM 1": "csFullGameList",
            "GLST 40": [int(game_id)],
        },
    }
    try:
        roster_response = await socket.send(packet, timeout=BLAZE_QUERY_TIMEOUT)
    except (TimeoutError, ConnectionError, OSError) as exc:
        await _pool.invalidate()
        raise EAApiError(
            code="BLAZE_QUERY_FAILED",
            message=f"Blaze 查询超时或连接中断: {exc}",
        ) from exc
    except ValueError as exc:
        # 单帧解码失败：连接本身仍可用，不必重建
        raise EAApiError(code="BLAZE_QUERY_FAILED", message=str(exc)) from exc

    parsed = BlazeData.player_list_handle(roster_response)
    if isinstance(parsed, str):
        raise EAApiError(code="BLAZE_QUERY_FAILED", message=parsed)
    room = parsed.get(int(game_id))
    if room is None and parsed:
        room = next(iter(parsed.values()))
    if not room:
        raise NotFoundError(resource=f"服务器 gameId={game_id} 的实时玩家数据")

    # 2. 管理 / VIP 名单与阵营取自 roster 的 ATTR；可选战绩走 Gateway HTTP
    #    （与 roster 串行避免共用 db 并发）。
    raw_normal = room.get("players") or []
    raw_queues = room.get("queues") or []
    raw_spectators = room.get("spectators") or []
    normal_pids = [int(p["pid"]) for p in raw_normal]

    attrs = room.get("attributes") or {}
    admin_ids = _attr_ids(attrs, "admins")
    vip_ids = _attr_ids(attrs, "vips")
    faction_by_team = _faction_map(attrs.get("level"))
    all_pids = (
        normal_pids + [int(p["pid"]) for p in raw_queues] + [int(p["pid"]) for p in raw_spectators]
    )
    stats_map: dict[int, BlazePlayerStats] = {}
    rank_map: dict[int, int] = {}
    if include_stats:
        # 排队 / 观战玩家的 roster 同样不带等级，一并查战绩估算
        async with get_bf1_client(db) as client:
            stats_map, rank_map = await _gather_stats(client, all_pids)

    # 3. 平台已绑定用户标记（db 此时已空闲）。
    registered_ids = await _fetch_registered_ids(db, all_pids)

    def _make(raw_player: dict) -> BlazePlayer:
        return _build_player(
            raw_player,
            admin_ids=admin_ids,
            vip_ids=vip_ids,
            registered_ids=registered_ids,
            stats_map=stats_map,
            rank_map=rank_map,
        )

    normal_players = [_make(p) for p in raw_normal]
    queued_players = [_make(p) for p in raw_queues]
    spectator_players = [_make(p) for p in raw_spectators]
    everyone = normal_players + queued_players + spectator_players

    summary = ServerPlayersSummary(
        online_admin_count=sum(1 for p in everyone if p.is_admin),
        online_vip_count=sum(1 for p in everyone if p.is_vip),
        online_registered_count=sum(1 for p in everyone if p.is_registered),
        rank_150_count=sum(1 for p in everyone if p.rank >= RANK_MAX),
    )

    # 仅对战两队进入列表；过渡态 / 未定队位玩家不成列，在线人数按实际成列的两队统计，
    # 避免因偶发哨兵队位导致「在线数」超过对战槽位。
    teams = _build_team_groups(normal_players, faction_by_team)
    battle_player_count = sum(team.count for team in teams)

    return ServerPlayersResponse(
        game_id=int(game_id),
        server_name=room.get("server_name"),
        max_players=int(room.get("max_player") or 0),
        player_count=battle_player_count,
        queue_count=len(queued_players),
        spectator_count=len(spectator_players),
        teams=teams,
        queued=queued_players,
        spectators=spectator_players,
        summary=summary,
        operation=_operation_progress(attrs),
        stats_included=include_stats,
        is_mock=False,
    )


async def fetch_game_list_snapshot(db: AsyncSession) -> list[dict[str, Any]]:
    """在连接池的已登录连接上拉一次全服快照，返回 NotifyGameListUpdate 的 UPDT 原始项。

    Result 只有 NGD/UPIN，游戏数据经推送分批到达，``DONE`` 为真表示结束。推送靠临时挂到
    ``socket.callback`` 上收集；回调也会收到其它请求（如玩家列表）的应答，按方法与类型过滤，
    不影响它们按 ID 匹配的 future。原始项含 HNET 等隐私字段，只留在内存交给调用方聚合，
    不得写日志或缓存。超时或任何异常向上抛，由调用方回退。
    """
    async with _snapshot_lock:
        socket = await _pool.get_socket(db)
        done = asyncio.get_running_loop().create_future()
        updates: list[dict[str, Any]] = []

        def _on_packet(packet: dict[str, Any]) -> None:
            if (
                packet.get("method") != "GameManager.NotifyGameListUpdate"
                or packet.get("type") != "Message"
            ):
                return
            data = packet.get("data") or {}
            updates.extend(data.get("UPDT") or [])
            if data.get("DONE") and not done.done():
                done.set_result(None)

        packet = {
            "method": "GameManager.getGameListSnapshot",
            "type": "Command",
            "data": {
                "CMGD 3": {"GGTY 0": 0, "GVER 1": "3779779"},
                "DNAM 1": "csFullGameList",
                "IGNO 0": 1,
                "LCAP 0": 65535,
                # PMIN 1 只要有人的服（约 140 个、1.8MB）；PMIN 0 会带上九千多个空服。
                "MMLC 3": {
                    "FRES 3": {"MAXS 0": 65535, "MINS 0": 0},
                    "RSZR 3": {"PCAP 0": 64, "PMIN 0": 1},
                },
            },
        }
        previous = socket.callback
        # BlazeSocket 把 callback 声明成静态方法、实例上按属性覆盖，mypy 认不出这种用法
        socket.callback = _on_packet  # type: ignore[method-assign]
        try:
            async with asyncio.timeout(GAME_LIST_SNAPSHOT_TIMEOUT):
                response = await socket.send(  # type: ignore[no-untyped-call]
                    packet, timeout=GAME_LIST_SNAPSHOT_TIMEOUT
                )
                if response.get("type") == "Error":
                    errc = (response.get("data") or {}).get("ERRC")
                    errc_text = hex(errc) if isinstance(errc, int) else errc
                    raise EAApiError(
                        code="BLAZE_QUERY_FAILED",
                        message=f"Blaze 快照返回错误 ERRC={errc_text}",
                    )
                await done
        except TimeoutError:
            # 收不齐推送不代表连接坏了；若在此重建，推送一直不来时每轮轮询都会重新登录
            raise
        except (ConnectionError, OSError):
            await _pool.invalidate()
            raise
        finally:
            socket.callback = previous  # type: ignore[method-assign]
        return updates
