"""审计日志 schema"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditLogItem(BaseModel):
    id: int
    user_id: int | None
    acting_persona_id: int
    # EA 侧实际执行的账号（群服务账号或个人留存的凭据），没有 EA 操作时为空
    executor_persona_id: int | None = None
    game: str
    server_id: int | None
    group_id: int | None = None
    action: str
    target_persona_id: int | None
    payload: dict[str, Any]
    result: str
    error_code: str | None
    error_message: str | None
    ip: str | None
    user_agent: str | None
    created_at: datetime


class AuditLogPage(BaseModel):
    items: list[AuditLogItem]
    total: int
    page: int
    page_size: int
