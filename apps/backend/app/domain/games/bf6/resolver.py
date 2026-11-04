"""BF6 名字 → nucleus：走 EA 官网战绩页搜索用的公开 Drop API，不需要登录。

- 搜的是 **EA 账号显示名**。Steam 玩家的 Steam 昵称和 EA 显示名不同就搜不到，官方也没有 Steam 维度。
- 查询要带当前赛季的 event id（官网搜索就是这么调的），它随赛季变，从 highlights 接口取。
- 200 时 ``playerStatsSummary``（本赛季有数据）或 ``noStatsData``（人在、本赛季没打）里有 userId，
  即 nucleus；206 ``MISSING_GAMER_NAME`` 表示没这个名字。
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import quote

import httpx

from app.domain.games.bf6.client import Bf6Error

DROP_BASE = "https://drop-api.ea.com"
GAME_SLUG = "battlefield-6"

Bf6Platform = Literal["ea", "psn", "xbox", "steam", "epic"]
# Drop API 的平台命名空间；Steam 没有，留空即不带过滤
PLATFORM_NAMESPACE: dict[str, str | None] = {
    "ea": "cem_ea_id",
    "psn": "ps3",
    "xbox": "xbox",
    "steam": None,
    "epic": "epic",
}

_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"))


@dataclass(frozen=True)
class ResolvedPlayer:
    nucleus_id: int
    display_name: str | None
    platform: str | None
    avatar_url: str | None
    # 本赛季在官网有没有数据；生涯数据与此无关，以 getStats 为准
    has_current_season_stats: bool


def normalize_name(name: str) -> str:
    """去首尾空白和零宽字符、合并连续空白、NFC 归一（中文名从别处复制来常带这些）。"""
    value = unicodedata.normalize("NFC", name.strip()).translate(_ZERO_WIDTH)
    return " ".join(value.split())


def _find_key(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        values: list[Any] = list(obj.values())
    elif isinstance(obj, list):
        values = obj
    else:
        return None
    for value in values:
        found = _find_key(value, key)
        if found is not None:
            return found
    return None


async def fetch_current_event(http: httpx.AsyncClient) -> str:
    try:
        response = await http.get(
            f"{DROP_BASE}/player/{GAME_SLUG}/highlights", params={"locale": "en"}
        )
    except httpx.HTTPError as e:
        raise Bf6Error(f"取当前赛季失败：{type(e).__name__}", retryable=True) from e
    if response.status_code != 200:
        raise Bf6Error(f"取当前赛季失败：HTTP {response.status_code}", retryable=True)
    event = _find_key(response.json(), "gameEvent")
    event_id = event.get("id") if isinstance(event, dict) else None
    if not event_id:
        raise Bf6Error("highlights 响应里没有 gameEvent.id")
    return str(event_id)


async def lookup(
    http: httpx.AsyncClient, name: str, event_id: str, platform: Bf6Platform | None
) -> ResolvedPlayer | None:
    """按显示名查 nucleus；名字不存在返回 None。"""
    params = {"gameSlug": GAME_SLUG, "eventName": event_id, "locale": "en", "source": "web_search"}
    namespace = PLATFORM_NAMESPACE.get(platform) if platform else None
    if namespace:
        params["platform"] = namespace
    try:
        response = await http.get(f"{DROP_BASE}/player/{quote(name, safe='')}/stats", params=params)
    except httpx.HTTPError as e:
        raise Bf6Error(f"查玩家失败：{type(e).__name__}", retryable=True) from e
    if response.status_code in (206, 404):
        return None
    if response.status_code != 200:
        raise Bf6Error(
            f"查玩家失败：HTTP {response.status_code}", retryable=response.status_code >= 500
        )
    data = response.json()
    summary = data.get("playerStatsSummary") or {}
    record = summary or data.get("noStatsData") or {}
    user_id = record.get("userId")
    if not user_id:
        return None
    avatar = record.get("userAvatar")
    return ResolvedPlayer(
        nucleus_id=int(user_id),
        display_name=record.get("playerDisplayName"),
        platform=record.get("platform"),
        avatar_url=(avatar.get("large") or avatar.get("medium"))
        if isinstance(avatar, dict)
        else None,
        has_current_season_stats=bool(summary),
    )
