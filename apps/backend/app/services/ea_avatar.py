"""EA 账号头像：按 EA 账号 ID 从 EA App 的接口取，各游戏通用"""

from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.domain.games.bf1.gateway_errors import gateway_failure
from app.services.bf1.gateway_factory import get_bf1_client


async def fetch_ea_avatar(db: AsyncSession, ea_user_id: int | None) -> str | None:
    """用号池账号查一次头像。取不到（号池没号、EA 失败、没设头像）返回 None，不打断绑定流程。"""
    if not ea_user_id:
        return None
    try:
        async with get_bf1_client(db) as client:
            res = await client.getPlayerByPd(ea_user_id)
    except AppError as e:
        logger.warning("EA 头像查询拿不到号池账号 ea_user_id={}: {}", ea_user_id, e.message)
        return None
    if (err := gateway_failure(res)) is not None:
        logger.warning("EA 头像查询失败 ea_user_id={}: {!r}", ea_user_id, err)
        return None
    avatar = res.get("avatar") if isinstance(res, dict) else None
    return avatar or None
