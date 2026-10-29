"""BF1 对局路由"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DbDep
from app.api.rate_limit import rate_limit
from app.schemas.bf1.rounds import RoundDetail
from app.services.bf1.round_service import get_round

router = APIRouter()

# 只读库或缓存，不占 EA 号，额度宽松，只防整站爬取
_read = rate_limit("read")


@router.get("/{round_id}", dependencies=[_read], response_model=RoundDetail)
async def get_round_route(round_id: int, db: DbDep) -> RoundDetail:
    return await get_round(db, round_id)
