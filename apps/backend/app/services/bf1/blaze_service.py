"""BF1 Blaze 服务：拉取服务器实时玩家列表

Blaze 是 EA 后端的二进制长连接协议，提供 Gateway 拿不到的房间实时名单（队伍 / 延迟 /
等级 / 语言）。本模块在协议层（``domain.ea.blaze_protocol``）之上做三件事：

1. 维护一个进程级 Blaze 连接池：单 worker 部署下复用同一条已登录连接，按连接年龄上限
   主动重建，避免每次查询都付出建连 + TLS + 登录的冷启动成本。
2. 封装 Blaze 登录序列：用账号池凭据取 Blaze authcode，经 redirector 拿到 Blaze 服务器
   地址，建立加密连接并完成 ``Authentication.login``。
3. 组装玩家列表：Blaze roster 叠加 ATTR 里的管理 / VIP 名单、平台已绑定用户标记，以及可选的
   生涯战绩（Blaze Stats.getStats 批量查询）。

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
from app.core import ea_budget, ea_metrics
from app.core.cache import Cache, get_cache
from app.core.config import get_settings
from app.domain.ea.account_pool import EACredentials
from app.domain.ea.blaze_protocol.socket import BlazeServerREQ, BlazeSocket
from app.domain.ea.data_handle import BlazeData
from app.domain.games.bf1.blaze_stats import career_stat_names, parse_career
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
from app.services.bf1.server_service import operation_map_list
from app.services.ea_account_service import EAAccountService

# Blaze 单条连接的最大存活时间（秒）。连接平时每分钟都有快照和跟踪器在用，EA 端断开、登出或
# 查询超时都会让连接失效并在下次使用时重建，所以不必频繁主动重登；只留一个长上限兜底未知的
# 会话过期。原先 300 秒，每天要重登近 600 次。探测时单条连接实测活过 1.5 小时。
CONNECTION_MAX_AGE_SECONDS = 6 * 3600
# 单次 Blaze 查询（含大体量 roster 解码）的超时。
BLAZE_QUERY_TIMEOUT = 20
# Blaze Stats.getStats 单个请求带多少个 personaId。2026-10-29 实测核心 1024 人、武器类别 512 人都能
# 一次返回，值与 64 人一批逐人一致；EA 每个请求有固定开销（武器 64 人约 1s、256 人不到 2s），
# 批越大总耗时越省。取 256，离测过的上限留一倍余量。
STATS_BATCH_SIZE = 256
# 生涯战绩按 personaId 缓存的时长（秒）。生涯数据只在回合结束时更新，刷新同一服务器时
# 大部分玩家直接命中缓存。
STATS_CACHE_TTL_SECONDS = 600
STATS_CACHE_PREFIX = "bf1:blaze_list_stats"
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

            if socket is not None:
                age = time.monotonic() - self._created_at
                reason = (
                    "到达寿命上限"
                    if socket.connect and getattr(socket, "authenticated", False)
                    else "连接已断开"
                )
                logger.info("Blaze 连接重建（{}），旧连接存活 {:.0f} 分钟", reason, age / 60)
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
            logger.warning("Blaze 登录请求失败: {!r}", exc)
            raise EAApiError(code="BLAZE_LOGIN_FAILED", message="Blaze 登录失败") from exc
        if not isinstance(response, dict) or response.get("type") == "Error":
            with contextlib.suppress(Exception):
                await socket.close()
            logger.warning("Blaze 登录返回异常: {}", str(response)[:500])
            raise EAApiError(code="BLAZE_LOGIN_FAILED", message="Blaze 登录返回异常")
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
            if self._socket is not None:
                age = time.monotonic() - self._created_at
                logger.info("Blaze 连接因查询失败作废，存活 {:.0f} 分钟", age / 60)
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


async def fetch_stats(
    db: AsyncSession, pids: list[int], names: dict[str, list[str]]
) -> dict[int, dict[str, float]]:
    """Blaze ``Stats.getStats`` 批量取生涯统计，返回 {pid: {统计名: 数值}}。

    names 为 {类别: 统计名列表}；每类每 STATS_BATCH_SIZE 人一个请求，全部并发发在同一条连接上。没有生涯数据
    的 pid 不在结果里。统计名写错会让整个请求报错，所以名单只来自已验证的映射与武器目录。
    """
    await ea_budget.acquire()
    socket = await _pool.get_socket(db)
    batches = [
        (cat, stat_names, pids[i : i + STATS_BATCH_SIZE])
        for cat, stat_names in names.items()
        if stat_names
        for i in range(0, len(pids), STATS_BATCH_SIZE)
    ]

    async def _one(cat: str, stat_names: list[str], batch: list[int]) -> list[tuple[int, dict]]:
        packet = {
            "method": "Stats.getStats",
            "type": "Command",
            "data": {"CAT  1": cat, "EID  40": batch, "NAME 41": stat_names},
        }
        ea_metrics.count_pids(len(batch))
        try:
            response = await socket.send(packet, timeout=BLAZE_QUERY_TIMEOUT)
        except (TimeoutError, ConnectionError, OSError) as exc:
            await _pool.invalidate()
            logger.warning("Blaze 查询超时或连接中断: {!r}", exc)
            raise EAApiError(code="BLAZE_QUERY_FAILED", message="Blaze 查询超时或连接中断") from exc
        if not isinstance(response, dict) or response.get("type") != "Result":
            raise EAApiError(
                code="BLAZE_STATS_FAILED",
                message=f"Blaze 战绩查询失败: {str((response or {}).get('data'))[:200]}",
            )
        rows = (((response.get("data") or {}).get("KSSV") or {}).get("No_Scope_Defined") or {}).get(
            "STAT"
        ) or []
        return [
            (int(row["EID"]), dict(zip(stat_names, map(float, row["STAT"]), strict=False)))
            for row in rows
        ]

    out: dict[int, dict[str, float]] = {}
    for rows in await asyncio.gather(*(_one(*b) for b in batches)):
        for pid, values in rows:
            out.setdefault(pid, {}).update(values)
    return out


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


async def _cache_set(cache: Cache | None, pid: int, entry: dict[str, Any]) -> None:
    if cache is None:
        return
    try:
        await cache.set(f"{STATS_CACHE_PREFIX}:{pid}", entry, ttl=STATS_CACHE_TTL_SECONDS)
    except Exception as exc:
        logger.warning(f"玩家 {pid} 战绩缓存写入失败: {exc}")


async def _gather_stats(
    db: AsyncSession, pids: list[int]
) -> tuple[dict[int, BlazePlayerStats], dict[int, int]]:
    """批量查询多名玩家的生涯战绩与等级，先读缓存，没命中的一次 Blaze 批量补齐。

    返回 ``stats_map`` 与 ``rank_map``（roster 多数不带等级，用生涯 rank 补齐）。Blaze 查询失败
    时降级为无战绩，不影响名单本身。
    """
    if not pids:
        return {}, {}
    cache = await _stats_cache()
    cached: dict[int, dict[str, Any]] = {}
    for pid in pids:
        hit = await _cache_get(cache, pid)
        if hit is not None:
            cached[pid] = hit
    misses = [pid for pid in pids if pid not in cached]
    if misses:
        try:
            values = await fetch_stats(db, misses, career_stat_names())
        except EAApiError as exc:
            logger.warning(f"{len(misses)} 名玩家战绩查询失败，降级为无战绩: {exc}")
            values = {}
        for pid, vals in values.items():
            career = parse_career(vals)
            entry = {
                "win_rate": career.win_rate,
                "kd": career.kd,
                "kpm": career.kpm,
                "time_hours": career.seconds / 3600 if career.seconds else None,
                "rank": career.rank,
            }
            cached[pid] = entry
            await _cache_set(cache, pid, entry)
    stats_map = {
        pid: BlazePlayerStats(**{k: v for k, v in e.items() if k != "rank"})
        for pid, e in cached.items()
    }
    rank_map = {pid: int(e["rank"]) for pid, e in cached.items() if e.get("rank") is not None}
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


async def get_operation_states(db: AsyncSession, game_ids: list[int]) -> dict[int, dict[str, Any]]:
    """一次 Blaze 查询取多台服的当前地图与行动进度，供自动换图轮询。查不到的服不在结果里。"""
    if not game_ids:
        return {}
    socket = await _pool.get_socket(db)
    packet = {
        "method": "GameManager.getGameDataFromId",
        "type": "Command",
        "data": {"DNAM 1": "csFullGameList", "GLST 40": [int(g) for g in game_ids]},
    }
    try:
        response = await socket.send(packet, timeout=BLAZE_QUERY_TIMEOUT)
    except (TimeoutError, ConnectionError, OSError) as exc:
        await _pool.invalidate()
        logger.warning("Blaze 查询超时或连接中断: {!r}", exc)
        raise EAApiError(code="BLAZE_QUERY_FAILED", message="Blaze 查询超时或连接中断") from exc
    parsed = BlazeData.player_list_handle(response)
    if isinstance(parsed, str):
        raise EAApiError(code="BLAZE_QUERY_FAILED", message=parsed)
    result: dict[int, dict[str, Any]] = {}
    for gid, room in parsed.items():
        attrs = room.get("attributes") or {}
        result[int(gid)] = {
            "map": attrs.get("level"),
            "mode": attrs.get("mode"),
            "progress": attrs.get("progress"),
            "state": attrs.get("operationstate"),
            "players": len(room.get("players") or []),
        }
    return result


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

    await ea_budget.acquire()
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
        logger.warning("Blaze 查询超时或连接中断: {!r}", exc)
        raise EAApiError(code="BLAZE_QUERY_FAILED", message="Blaze 查询超时或连接中断") from exc
    except ValueError as exc:
        # 单帧解码失败：连接本身仍可用，不必重建
        logger.warning("Blaze 名单解码失败: {!r}", exc)
        raise EAApiError(code="BLAZE_QUERY_FAILED", message="Blaze 返回数据解析失败") from exc

    parsed = BlazeData.player_list_handle(roster_response)
    if isinstance(parsed, str):
        raise EAApiError(code="BLAZE_QUERY_FAILED", message=parsed)
    room = parsed.get(int(game_id))
    if room is None and parsed:
        room = next(iter(parsed.values()))
    if not room:
        raise NotFoundError(resource=f"服务器 gameId={game_id} 的实时玩家数据")

    # 2. 管理 / VIP 名单与阵营取自 roster 的 ATTR；可选战绩走同一条 Blaze 连接批量查。
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
        # 排队 / 观战玩家的 roster 同样不带等级，一并查
        stats_map, rank_map = await _gather_stats(db, all_pids)

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


async def lookup_online_persona(db: AsyncSession, name: str) -> tuple[int, str] | None:
    """按昵称精确查 persona（不区分大小写），返回 (personaId, 昵称)。

    ``UserSessions.lookupUser`` 只认当前在线的人，离线或不存在都报 USER_NOT_FOUND，返回 None。
    """
    socket = await _pool.get_socket(db)
    packet = {"method": "UserSessions.lookupUser", "type": "Command", "data": {"NAME 1": name}}
    try:
        res = await socket.send(packet, timeout=BLAZE_QUERY_TIMEOUT)
    except (TimeoutError, ConnectionError, OSError):
        await _pool.invalidate()
        raise
    user = (res.get("data") or {}).get("USER") if res.get("type") == "Result" else None
    if not user or not user.get("ID"):
        return None
    return int(user["ID"]), user.get("NAME") or name


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
