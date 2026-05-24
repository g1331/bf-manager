"""审计日志查询路由

普通用户只能看自己的操作日志；平台 admin 可以看全部，并按 game/server/action 过滤。
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbDep
from app.schemas.audit import AuditLogItem, AuditLogPage
from app.services.audit_service import AuditService

router = APIRouter()


@router.get("", response_model=AuditLogPage)
async def list_audit_logs(
    db: DbDep,
    user: CurrentUser,
    game: str | None = Query(None, max_length=16),
    server_id: int | None = Query(None),
    action: str | None = Query(None, max_length=64),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> AuditLogPage:
    # 非 admin 用户只能看自己产生的日志
    target_user_id = None if user.role == "admin" else user.id

    service = AuditService(db)
    rows, total = await service.list(
        game=game,
        server_id=server_id,
        action=action,
        user_id=target_user_id,
        page=page,
        page_size=page_size,
    )
    items = [
        AuditLogItem(
            id=log.id,
            user_id=log.user_id,
            acting_persona_id=log.acting_persona_id,
            game=log.game,
            server_id=log.server_id,
            action=log.action,
            target_persona_id=log.target_persona_id,
            payload=log.payload,
            result=log.result,
            error_code=log.error_code,
            error_message=log.error_message,
            ip=log.ip,
            user_agent=log.user_agent,
            created_at=log.created_at,
        )
        for log in rows
    ]
    return AuditLogPage(items=items, total=total, page=page, page_size=page_size)
