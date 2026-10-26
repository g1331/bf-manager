"""BF1 战队查询

详情走 EA Gateway：getPlatoon 基本信息、getMembers 成员（一页 100 人就是战队上限）、
getServersWithPlayers 成员正在玩的服务器。搜索走 findByPartialName：只按战队名模糊匹配（不含简称），
关键字至少 3 个字符，每次最多 10 条。战队只在 Gateway 上，Blaze 没有 Clubs 组件（实测 0x4002）。
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import EAApiError, NotFoundError
from app.core.cache import get_cache
from app.domain.games.bf1.maps import normalize_emblem_url
from app.schemas.bf1.platoon import (
    PlatoonDetail,
    PlatoonMember,
    PlatoonRole,
    PlatoonSearchItem,
    PlatoonServer,
)
from app.services.bf1.gateway_factory import get_bf1_client
from app.services.bf1.server_service import _to_summary
from app.services.bf1.stats_service import _build_platoon

GUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
# 2026-10-26 对照 gametools detailedplatoon：role9 General、role6 Colonel、role3 Lieutenant、role0 Private
ROLES: dict[str, PlatoonRole] = {
    "role9": "general",
    "role6": "colonel",
    "role3": "lieutenant",
    "role0": "private",
}
ROLE_ORDER = {r: i for i, r in enumerate(["general", "colonel", "lieutenant", "private", None])}

DETAIL_TTL = 180
SEARCH_TTL = 600
SEARCH_MIN_LEN = 3
SEARCH_PAGE_SIZE = 10  # EA 上限，超过报「11 > 10」


def _member(raw: dict[str, Any]) -> PlatoonMember | None:
    try:
        pid = int(raw["personaId"])
    except (KeyError, TypeError, ValueError):
        return None
    return PlatoonMember(
        persona_id=pid,
        name=str(raw.get("displayName") or pid),
        role=ROLES.get(str(raw.get("role"))),
        avatar_url=raw.get("avatar") or None,
    )


def build_detail(info: dict[str, Any], members: Any, servers: Any) -> PlatoonDetail:
    """三个 EA 返回拼成详情。纯函数，便于单测；成员与服务器取不到时留空，不影响基本信息。"""
    base = _build_platoon(info)
    if base is None:
        raise NotFoundError(resource="战队")
    result = info["result"]
    join = result.get("joinConfig") or {}
    raw_members = members.get("result") if isinstance(members, dict) else None
    member_list = [m for m in (_member(r) for r in raw_members or []) if m]
    member_list.sort(key=lambda m: (ROLE_ORDER[m.role], m.name.lower()))
    server_list = []
    if isinstance(servers, dict):
        for entry in servers.get("result") or []:
            raw_server = entry.get("server") or {}
            if not raw_server.get("gameId"):
                continue
            shown = (entry.get("platoon") or {}).get("displayMembers") or []
            server_list.append(
                PlatoonServer(
                    server=_to_summary(raw_server),
                    # displayMembers 的 role 是 role-2 之类，与成员列表不同，这里不取职位
                    members=[
                        m.model_copy(update={"role": None})
                        for m in (_member(r) for r in shown)
                        if m
                    ],
                )
            )
    try:
        created_at = int(result.get("dateCreated"))
    except (TypeError, ValueError):
        created_at = None
    return PlatoonDetail(
        **base.model_dump(),
        created_at=created_at,
        free_join=bool(join.get("isFreeJoin")),
        can_apply=bool(join.get("canApplyMembership")),
        members=member_list,
        servers=server_list,
    )


async def get_platoon_detail(db: AsyncSession, guid: str) -> PlatoonDetail:
    guid = guid.lower()
    if not GUID_RE.match(guid):
        raise NotFoundError(resource="战队")
    cache = await get_cache()
    key = f"bf1:platoon:{guid}"
    if cached := await cache.get(key):
        return PlatoonDetail.model_validate(cached)
    async with get_bf1_client(db) as client:
        info = await client.getPlatoon(guid)
        if isinstance(info, str):
            if "找不到" in info:
                raise NotFoundError(resource="战队")
            raise EAApiError(code="EA_PLATOON_FETCH_FAILED", message=f"EA Gateway 查询失败: {info}")
        # 同一个 client 串行调用：并发时 session 失效会触发两次重新登录
        members = await client.getMembers(guid)
        servers = await client.getServersWithPlayers(guid)
    detail = build_detail(info, members, servers)
    await cache.set(key, detail.model_dump(mode="json"), ttl=DETAIL_TTL)
    return detail


def build_search(res: Any) -> list[PlatoonSearchItem]:
    """findByPartialName 的返回转成搜索结果。纯函数，便于单测。"""
    raw = res.get("result") if isinstance(res, dict) else None
    return [
        PlatoonSearchItem(
            guid=p["guid"],
            tag=p.get("tag"),
            name=p.get("name"),
            size=p.get("size"),
            emblem_url=normalize_emblem_url(p.get("emblem")),
        )
        for p in raw or []
        if isinstance(p, dict) and p.get("guid")
    ]


async def search_platoons(db: AsyncSession, name: str) -> list[PlatoonSearchItem]:
    name = name.strip()
    if len(name) < SEARCH_MIN_LEN:
        return []
    cache = await get_cache()
    key = f"bf1:platoon-search:{name.lower()}"
    if (cached := await cache.get(key)) is not None:
        return [PlatoonSearchItem.model_validate(i) for i in cached]
    async with get_bf1_client(db) as client:
        res = await client.findByPartialName(name, page_size=SEARCH_PAGE_SIZE)
    if isinstance(res, str):
        raise EAApiError(code="EA_PLATOON_SEARCH_FAILED", message=f"EA Gateway 查询失败: {res}")
    items = build_search(res)
    await cache.set(key, [i.model_dump() for i in items], ttl=SEARCH_TTL)
    return items
