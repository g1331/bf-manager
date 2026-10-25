"""BF1 玩家 persona 查询服务"""

from __future__ import annotations

import asyncio
from collections import Counter

import httpx
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import EAApiError, NotFoundError
from app.core.cache import get_cache
from app.domain.games.bf1.gateway import BF1GatewayClient
from app.schemas.bf1.player import PersonaBrief, PersonaSearchResult
from app.services.bf1 import blaze_service
from app.services.bf1.gateway_factory import get_bf1_client


async def _fetch_sal_avatar(
    client: BF1GatewayClient, display_name: str, persona_id: int
) -> str | None:
    """通过 SAL SearchPlayer 反查 persona 头像。

    EA `RSP.getPersonasByIds` 当前对所有账号返回 avatar=""，但同 EA Desktop 通道
    的 SAL GraphQL SearchPlayer 仍能拿到 eaavatarservice.akamaized.net 上的官方
    头像 URL。借用 displayName 反查同 personaId 一项的 avatar，属于 EA 原生通道，
    不引入第三方服务依赖。失败/未匹配一律返回 None，由上层决定是否继续兜底。
    """
    try:
        res = await client.getPersonasByName(display_name)
    except Exception as exc:
        logger.debug(f"SAL avatar fetch failed for {persona_id}: {exc}")
        return None
    if not isinstance(res, dict):
        return None
    for p in res.get("personas", []) or []:
        if p.get("personaId") == persona_id:
            return p.get("avatar") or None
    return None


async def _fetch_gametools_avatar(persona_id: int) -> str | None:
    """SAL 拿不到时退到 gametools 的 player 接口取头像。

    gametools 是社区中转，返回的是同一份 eaavatarservice 的头像数据，仅作为
    SAL 异常（401 / 限流 / 网络异常 / 同名匹配失败）的兜底路径。任何失败一律
    静默返回 None，保证主流程不被三方服务波动拖累。
    """
    url = "https://api.gametools.network/bf1/player/"
    params = {
        "playerid": str(persona_id),
        "platform": "pc",
        "skip_battlelog": "false",
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, params=params, headers={"accept": "application/json"})
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception as exc:
        logger.debug(f"gametools avatar fetch failed for {persona_id}: {exc}")
        return None
    if not isinstance(data, dict) or data.get("errors"):
        return None
    avatar = data.get("avatar")
    return avatar or None


async def _fetch_gametools_persona(name: str) -> PersonaBrief | None:
    """按昵称精确查 persona（gametools，离线也能查到）。失败或查无此人返回 None。"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://api.gametools.network/bf1/player/",
                params={"name": name, "platform": "pc"},
                headers={"accept": "application/json"},
            )
        data = resp.json() if resp.status_code == 200 else None
    except Exception as exc:
        logger.debug(f"gametools persona lookup failed for {name}: {exc}")
        return None
    if not isinstance(data, dict) or not data.get("id") or not data.get("userName"):
        return None
    return PersonaBrief(
        persona_id=int(data["id"]), display_name=data["userName"], avatar_url=data.get("avatar")
    )


AVATAR_CACHE_KEY = "bf1:avatar:{}"
AVATAR_TTL = 7 * 86400
# 没取到（无头像或 gametools 波动）的隔一小时再试
MISSING_AVATAR_TTL = 3600
AVATAR_CONCURRENCY = 8


async def get_avatars(persona_ids: list[int]) -> dict[int, str | None]:
    """批量取头像（服务器成员名单用），按 persona 缓存。

    RSP 名单里的 avatar 恒为空，逐个走 SAL 会把一两百个请求压到号池上，所以批量场景只走
    gametools 单人接口（它的批量接口常超时），限并发、结果缓存 7 天。
    """
    cache = await get_cache()
    result: dict[int, str | None] = {}
    misses: list[int] = []
    for pid in persona_ids:
        cached = await cache.get(AVATAR_CACHE_KEY.format(pid))
        if cached is None:
            misses.append(pid)
        else:
            result[pid] = cached or None
    sem = asyncio.Semaphore(AVATAR_CONCURRENCY)

    async def fetch(pid: int) -> None:
        async with sem:
            url = await _fetch_gametools_avatar(pid)
        result[pid] = url
        await cache.set(
            AVATAR_CACHE_KEY.format(pid), url or "", ttl=AVATAR_TTL if url else MISSING_AVATAR_TTL
        )

    await asyncio.gather(*(fetch(pid) for pid in misses))
    return result


async def _playtime_hours(client: BF1GatewayClient, persona_id: int) -> int | None:
    """取该 persona 的 BF1 生涯时长（小时，取整）。无生涯 / 异常返回 None。"""
    try:
        data = await client.detailedStatsByPersonaId(persona_id)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    seconds = (data.get("result") or {}).get("basicStats", {}).get("timePlayed")
    if not isinstance(seconds, (int, float)):
        return None
    return int(seconds // 3600)


class BF1PlayerService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def search_by_name(self, name: str) -> PersonaSearchResult:
        async with get_bf1_client(self.db) as client:
            res = await client.getPersonasByName(name)
            if not isinstance(res, dict):
                raise EAApiError(
                    code="EA_PERSONA_SEARCH_FAILED",
                    message=f"EA Gateway 查询失败: {res}",
                )
            personas_raw = res.get("personas", []) or []
            personas = [
                PersonaBrief(
                    persona_id=int(p.get("personaId") or p.get("pidId") or 0),
                    display_name=p.get("displayName", ""),
                    avatar_url=p.get("avatar"),
                )
                for p in personas_raw
                if (p.get("personaId") or p.get("pidId"))
            ]
            if not any(p.display_name.lower() == name.lower() for p in personas):
                exact = await self._lookup_exact(name)
                if exact and all(p.persona_id != exact.persona_id for p in personas):
                    personas.insert(0, exact)
            await self._annotate_playtime_for_duplicates(client, personas)
            return PersonaSearchResult(query=name, personas=personas)

    async def _lookup_exact(self, name: str) -> PersonaBrief | None:
        """SAL 是模糊搜索（忽略连字符、只取前 20 条、可能受隐私设置影响），没命中原名时
        先问 gametools（离线也能查），再问 Blaze lookupUser（官方，但只认在线玩家）。"""
        found = await _fetch_gametools_persona(name)
        if found:
            return found
        try:
            hit = await blaze_service.lookup_online_persona(self.db, name)
        except Exception as exc:
            logger.debug(f"Blaze lookupUser failed for {name}: {exc}")
            return None
        return PersonaBrief(persona_id=hit[0], display_name=hit[1]) if hit else None

    async def _annotate_playtime_for_duplicates(
        self, client: BF1GatewayClient, personas: list[PersonaBrief]
    ) -> None:
        """EA 允许多账号共用同一昵称：仅当结果出现重名时，为每个重名候选回填 BF1 生涯时长，
        帮管理员区分真号（>0）与空号（0，对其加 V / 服管会报玩家不存在）。无重名则不查，省开销。
        """
        counts = Counter(p.display_name.lower() for p in personas if p.display_name)
        dups = [p for p in personas if p.display_name and counts[p.display_name.lower()] > 1]
        if not dups:
            return
        hours = await asyncio.gather(*[_playtime_hours(client, p.persona_id) for p in dups])
        for persona, h in zip(dups, hours, strict=True):
            persona.time_played_hours = h

    async def get_by_id(self, persona_id: int) -> PersonaBrief:
        async with get_bf1_client(self.db) as client:
            res = await client.getPersonasByIds([persona_id])
            if not isinstance(res, dict):
                raise EAApiError(
                    code="EA_PERSONA_FETCH_FAILED",
                    message=f"EA Gateway 查询失败: {res}",
                )
            result = res.get("result", {}) or {}
            info = result.get(str(persona_id)) or result.get("personas", {}).get(str(persona_id))
            if not info:
                raise NotFoundError(resource=f"persona {persona_id}")
            display_name = info.get("displayName", "")
            avatar = info.get("avatar") or None
            if not avatar and display_name:
                avatar = await _fetch_sal_avatar(client, display_name, persona_id)
        if not avatar:
            avatar = await _fetch_gametools_avatar(persona_id)
        return PersonaBrief(
            persona_id=persona_id,
            display_name=display_name,
            avatar_url=avatar,
        )
