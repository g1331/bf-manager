"""BF1 玩家 persona 查询服务"""

from __future__ import annotations

import httpx
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import EAApiError, NotFoundError
from app.domain.games.bf1.gateway import BF1GatewayClient
from app.schemas.bf1.player import PersonaBrief, PersonaSearchResult
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
            return PersonaSearchResult(query=name, personas=personas)

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
