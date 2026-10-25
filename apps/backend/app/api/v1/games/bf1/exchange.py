"""BF1 交换与行动路由（公开访问）"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Query

from app.api.deps import DbDep
from app.schemas.bf1.exchange import Campaign, ExchangeSnapshot
from app.services.bf1.exchange_service import get_campaign, get_exchange, list_exchange_periods

router = APIRouter()


@router.get("/exchange", response_model=ExchangeSnapshot)
async def exchange(
    db: DbDep,
    on: date | None = Query(None, alias="date", description="北京时间日期，取当天生效的那一期"),
) -> ExchangeSnapshot:
    return await get_exchange(db, on)


@router.get("/exchange/periods", response_model=list[datetime])
async def exchange_periods(db: DbDep) -> list[datetime]:
    return await list_exchange_periods(db)


@router.get("/campaign", response_model=Campaign | None)
async def campaign(db: DbDep) -> Campaign | None:
    return await get_campaign(db)
