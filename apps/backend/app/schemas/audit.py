"""审计日志 schema"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditLogItem(BaseModel):
    id: int
    user_id: int | None
    acting_persona_id: int
    game: str
    server_id: int | None
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
