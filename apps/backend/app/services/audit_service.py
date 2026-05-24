"""跨游戏审计日志服务"""

from __future__ import annotations

from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


class AuditService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record(
        self,
        *,
        user_id: int | None,
        acting_persona_id: int,
        game: str,
        action: str,
        server_id: int | None = None,
        target_persona_id: int | None = None,
        payload: dict[str, Any] | None = None,
        result: str = "success",
        error_code: str | None = None,
        error_message: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLog:
        log = AuditLog(
            user_id=user_id,
            acting_persona_id=acting_persona_id,
            game=game,
            action=action,
            server_id=server_id,
            target_persona_id=target_persona_id,
            payload=payload or {},
            result=result,
            error_code=error_code,
            error_message=error_message,
            ip=ip,
            user_agent=user_agent,
        )
        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)
        return log

    async def list(
        self,
        *,
        game: str | None = None,
        server_id: int | None = None,
        action: str | None = None,
        user_id: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[AuditLog], int]:
        base = select(AuditLog)
        if game:
            base = base.where(AuditLog.game == game)
        if server_id is not None:
            base = base.where(AuditLog.server_id == server_id)
        if action:
            base = base.where(AuditLog.action == action)
        if user_id is not None:
            base = base.where(AuditLog.user_id == user_id)

        count_stmt = select(func.count()).select_from(base.subquery())
        total = int((await self.db.scalar(count_stmt)) or 0)

        page = max(page, 1)
        page_size = max(min(page_size, 100), 1)
        list_stmt = (
            base.order_by(desc(AuditLog.created_at)).offset((page - 1) * page_size).limit(page_size)
        )
        rows = list((await self.db.scalars(list_stmt)).all())
        return rows, total
