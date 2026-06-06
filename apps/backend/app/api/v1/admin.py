"""平台运维统计路由（仅平台 admin 可访问）。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentAdmin
from app.schemas.admin import AdminMetrics
from app.services.metrics_service import read_metrics

router = APIRouter()


@router.get("/metrics", response_model=AdminMetrics)
async def get_admin_metrics(_user: CurrentAdmin) -> AdminMetrics:
    return await read_metrics()
