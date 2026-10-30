"""BF1 玩家所在服缓存

全服统计每轮快照成功时，把各服名单倒排成 pid → (game_id, 位置) 写进一个 Redis hash，
群成员的在线状态按 pid 直接 HMGET，不再请求 EA。整张表每轮原子替换，TTL 只留几轮：
快照连续失败（回退 searchServers 没有名单）时状态自然过期，不会一直显示旧服。

快照只含有人的服，所以“查不到”只说明不在任何服里，可能离线，也可能停在主菜单。
"""

from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger
from redis.exceptions import RedisError

from app.core.cache import get_redis
from app.services.bf1.server_roster_service import SLOT_NAMES, Rosters

PRESENCE_KEY = "bfm:bf1:presence"
# 三轮没刷新就当作不知道
PRESENCE_TTL = 180
# hash 里记录本轮时间的字段，pid 都是数字，不会撞名
_TS_FIELD = "_ts"


def encode_rosters(rosters: Rosters) -> dict[str, str]:
    """名单倒排成 hash 字段：pid → "game_id:位置"。同一人出现在两个服时留后一个。纯函数，便于单测。"""
    return {
        str(pid): f"{gid}:{slot}"
        for gid, players in rosters.items()
        for pid, (slot, _name) in players.items()
        if slot in SLOT_NAMES
    }


def decode_entry(raw: str | None) -> tuple[int, str] | None:
    """hash 值还原成 (game_id, 位置名)；位置名见 SLOT_NAMES。脏值返回 None。"""
    if not raw:
        return None
    gid, _, slot = raw.partition(":")
    try:
        name = SLOT_NAMES.get(int(slot))
        return (int(gid), name) if name else None
    except ValueError:
        return None


async def write_presence(rosters: Rosters) -> None:
    mapping = encode_rosters(rosters)
    mapping[_TS_FIELD] = str(int(datetime.now(UTC).timestamp()))
    tmp = f"{PRESENCE_KEY}:tmp"
    r = await get_redis()
    async with r.pipeline(transaction=True) as pipe:
        pipe.delete(tmp)
        # redis-py 的 Mapping 注解按不变泛型写，dict[str, str] 对不上
        pipe.hset(tmp, mapping=mapping)  # type: ignore[arg-type]
        pipe.expire(tmp, PRESENCE_TTL)
        pipe.rename(tmp, PRESENCE_KEY)
        await pipe.execute()


async def read_presence(
    pids: list[int],
) -> tuple[datetime | None, dict[int, tuple[int, str]]]:
    """按 pid 查所在服。返回 (本轮快照时间, pid → (game_id, 位置名))。

    缓存过期或 Redis 不可用时时间为 None，调用方据此显示“状态暂不可用”。
    """
    try:
        r = await get_redis()
        values = await r.hmget(PRESENCE_KEY, [_TS_FIELD, *map(str, pids)])
    except RedisError as e:
        logger.warning("BF1 presence cache read failed: {}", e)
        return None, {}
    ts_raw, *entries = values
    if not ts_raw:
        return None, {}
    found: dict[int, tuple[int, str]] = {}
    for pid, raw in zip(pids, entries, strict=True):
        entry = decode_entry(raw)  # type: ignore[arg-type]  # decode_responses=True，只会是 str
        if entry is not None:
            found[pid] = entry
    return datetime.fromtimestamp(int(ts_raw), UTC), found
