"""BF1 玩家 persona 查询服务"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import EAApiError, NotFoundError
from app.schemas.bf1.player import PersonaBrief, PersonaSearchResult
from app.services.bf1.gateway_factory import get_bf1_client


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
            avatar = info.get("avatar") or None
            return PersonaBrief(
                persona_id=persona_id,
                display_name=info.get("displayName", ""),
                avatar_url=avatar,
            )
