"""BF1 战队路由"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import DbDep
from app.api.rate_limit import rate_limit
from app.schemas.bf1.platoon import PlatoonDetail, PlatoonSearchItem
from app.services.bf1.platoon_service import get_platoon_detail, search_platoons

router = APIRouter()

# 这些接口会用到 EA 账号池或 Blaze 连接，按 IP / 账号限流并计入公共 EA 预算
_lookup = rate_limit("lookup")


@router.get("", dependencies=[_lookup], response_model=list[PlatoonSearchItem])
async def search(
    db: DbDep,
    name: str = Query(..., max_length=64, description="战队名或简称，少于 3 个字符返回空列表"),
) -> list[PlatoonSearchItem]:
    return await search_platoons(db, name)


@router.get("/{guid}", dependencies=[_lookup], response_model=PlatoonDetail)
async def get_platoon(guid: str, db: DbDep) -> PlatoonDetail:
    return await get_platoon_detail(db, guid)
