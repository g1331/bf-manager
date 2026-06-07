"""BF1 Blaze 服务：拉取服务器实时玩家列表

Blaze 是 EA 后端的二进制长连接协议，提供 Gateway 拿不到的房间实时名单（队伍 / 延迟 /
等级 / 语言）。本模块在协议层（``domain.ea.blaze_protocol``）之上做三件事：

1. 维护一个进程级 Blaze 连接池：单 worker 部署下复用同一条已登录连接，按连接年龄上限
   主动重建，避免每次查询都付出建连 + TLS + 登录的冷启动成本。
2. 封装 Blaze 登录序列：用账号池凭据取 Blaze authcode，经 redirector 拿到 Blaze 服务器
   地址，建立加密连接并完成 ``Authentication.login``。
3. 组装玩家列表：Blaze roster 叠加 RSP 管理 / VIP 名单、平台已绑定用户标记，以及可选的
   生涯战绩（并发限流合并）。

连接池为进程级单例，``close_blaze_pool`` 在 FastAPI lifespan 关闭时调用。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import Iterable
from pathlib import Path

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import EAApiError, NotFoundError
from app.core.config import get_settings
from app.domain.ea.account_pool import EACredentials
from app.domain.ea.blaze_protocol.socket import BlazeServerREQ, BlazeSocket
from app.domain.ea.data_handle import BlazeData
from app.domain.games.bf1.maps import MapData
from app.models.ea_binding import EaBinding
from app.schemas.bf1.server import (
    BlazePlayer,
    BlazePlayerStats,
    BlazeTeamGroup,
    ServerPlayersResponse,
    ServerPlayersSummary,
)
from app.services.bf1.gateway_factory import get_bf1_client
from app.services.bf1.server_service import _to_extras
from app.services.ea_account_service import EAAccountService

# Blaze 单条连接的最大存活时间（秒）。超龄主动重建，规避 EA 端静默断开后我方仍误判可用。
CONNECTION_MAX_AGE_SECONDS = 300
# 单次 Blaze 查询（含大体量 roster 解码）的超时。
BLAZE_QUERY_TIMEOUT = 20
# 并发查询生涯战绩的上限，控制对 EA Gateway 的瞬时压力，避免触发限流。
STATS_CONCURRENCY = 8
# BF1 满级。
RANK_MAX = 150
# Blaze TIDX 中表示「排队 / 旁观」而非真实队伍的哨兵值。
TEAM_SENTINEL = 65535

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
        name = response.get("data", {}).get("DSNM")
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


async def _gather_stats(client: object, pids: list[int]) -> dict[int, BlazePlayerStats]:
    """并发查询多名玩家的生涯战绩，信号量限流，单个失败降级为无战绩。"""
    if not pids:
        return {}
    semaphore = asyncio.Semaphore(STATS_CONCURRENCY)

    async def _one(pid: int) -> tuple[int, BlazePlayerStats | None]:
        async with semaphore:
            try:
                res = await client.detailedStatsByPersonaId(pid)  # type: ignore[attr-defined]
            except Exception as exc:
                logger.warning(f"玩家 {pid} 战绩查询失败，降级为无战绩: {exc}")
                return pid, None
            if not isinstance(res, dict):
                return pid, None
            basic = (res.get("result") or {}).get("basicStats") or {}
            if not basic:
                return pid, None
            return pid, _stats_from_basic(basic)

    results = await asyncio.gather(*[_one(pid) for pid in pids])
    return {pid: stats for pid, stats in results if stats is not None}


def _extract_member_ids(detail_res: object) -> tuple[set[int], set[int]]:
    """从 getFullServerDetails 响应解析在线判定所需的 admin / vip persona 集合。"""
    if not isinstance(detail_res, dict):
        return set(), set()
    raw = detail_res.get("result") or {}
    if not raw:
        return set(), set()
    extras = _to_extras(raw)
    return (
        {member.persona_id for member in extras.admins},
        {member.persona_id for member in extras.vips},
    )


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
) -> BlazePlayer:
    pid = int(raw_player["pid"])
    return BlazePlayer(
        persona_id=pid,
        display_name=raw_player.get("display_name") or "",
        rank=int(raw_player.get("rank") or 0),
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


def _faction_map(detail_res: object) -> dict[int, str]:
    """从服务器当前地图查 BF1 阵营对阵表，得出 {team_id: 阵营名}。

    BF1 的对阵阵营（法国 / 德意志帝国等）由当前地图固定决定，不在 Blaze roster 内，
    需用 `getFullServerDetails` 返回的 `serverInfo.mapName` 查 `MapData.MapTeamDict`：
    Blaze TIDX 0 对应该图 Team1，TIDX 1 对应 Team2。未知地图返回空映射，前端回退「队伍 N」。
    """
    if not isinstance(detail_res, dict):
        return {}
    raw = detail_res.get("result") or {}
    map_name = (raw.get("serverInfo") or {}).get("mapName")
    entry = MapData.MapTeamDict.get(map_name) if map_name else None
    if not entry:
        return {}
    return {0: entry["Team1"], 1: entry["Team2"]}


def _build_team_groups(
    players: list[BlazePlayer], faction_by_team: dict[int, str]
) -> list[BlazeTeamGroup]:
    """把在场玩家按 Blaze TIDX 分成队伍组，按 team_id 升序（通常得到两组）。"""
    by_team: dict[int, list[BlazePlayer]] = {}
    for player in players:
        by_team.setdefault(player.team, []).append(player)
    groups: list[BlazeTeamGroup] = []
    for team_id in sorted(by_team):
        members = by_team[team_id]
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

    parsed = BlazeData.player_list_handle(roster_response)
    if isinstance(parsed, str):
        raise EAApiError(code="BLAZE_QUERY_FAILED", message=parsed)
    room = parsed.get(int(game_id))
    if room is None and parsed:
        room = next(iter(parsed.values()))
    if not room:
        raise NotFoundError(resource=f"服务器 gameId={game_id} 的实时玩家数据")

    # 2. RSP 管理 / VIP 名单与可选战绩（走 Gateway HTTP，与 roster 串行避免共用 db 并发）。
    raw_normal = room.get("players") or []
    raw_queues = room.get("queues") or []
    raw_spectators = room.get("spectators") or []
    normal_pids = [int(p["pid"]) for p in raw_normal]

    async with get_bf1_client(db) as client:
        detail_res = await client.getFullServerDetails(int(game_id))
        admin_ids, vip_ids = _extract_member_ids(detail_res)
        faction_by_team = _faction_map(detail_res)
        stats_map = await _gather_stats(client, normal_pids) if include_stats else {}

    # 3. 平台已绑定用户标记（db 此时已空闲）。
    all_pids = (
        normal_pids + [int(p["pid"]) for p in raw_queues] + [int(p["pid"]) for p in raw_spectators]
    )
    registered_ids = await _fetch_registered_ids(db, all_pids)

    def _make(raw_player: dict) -> BlazePlayer:
        return _build_player(
            raw_player,
            admin_ids=admin_ids,
            vip_ids=vip_ids,
            registered_ids=registered_ids,
            stats_map=stats_map,
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

    return ServerPlayersResponse(
        game_id=int(game_id),
        server_name=room.get("server_name"),
        max_players=int(room.get("max_player") or 0),
        player_count=len(normal_players),
        queue_count=len(queued_players),
        spectator_count=len(spectator_players),
        teams=_build_team_groups(normal_players, faction_by_team),
        queued=queued_players,
        spectators=spectator_players,
        summary=summary,
        stats_included=include_stats,
        is_mock=False,
    )
