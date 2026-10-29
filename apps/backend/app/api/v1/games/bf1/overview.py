"""BF1 全服统计路由（只读缓存，公开访问）"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.rate_limit import rate_limit
from app.schemas.bf1.overview import BF1Overview
from app.services.bf1.overview_service import read_overview_cache

router = APIRouter()

# 只读库或缓存，不占 EA 号，额度宽松，只防整站爬取
_read = rate_limit("read")


@router.get("", dependencies=[_read], response_model=BF1Overview)
async def get_overview() -> BF1Overview:
    # 数据由后台定时任务轮询 EA 聚合后写入 Redis，这里只读缓存，不触发实时全量拉取。
    return await read_overview_cache()
