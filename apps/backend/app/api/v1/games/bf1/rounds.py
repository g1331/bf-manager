"""BF1 对局路由"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DbDep
from app.schemas.bf1.rounds import RoundDetail
from app.services.bf1.round_service import get_round

router = APIRouter()


@router.get("/{round_id}", response_model=RoundDetail)
async def get_round_route(round_id: int, db: DbDep) -> RoundDetail:
    return await get_round(db, round_id)
